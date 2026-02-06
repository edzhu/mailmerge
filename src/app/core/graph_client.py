"""Microsoft Graph client integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Any, Callable, Mapping
from urllib.parse import quote

import requests

from app.core.errors import GraphClientError, OptionalDependencyError

_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"
_DEFAULT_GRAPH_BASE_URL = "https://graph.microsoft.com"
_DEFAULT_TOKEN_REFRESH_BUFFER = timedelta(seconds=120)
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_RETRY_BACKOFF_BASE = 0.5
_RESPONSE_SNIPPET_LIMIT = 200

Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


def _load_msal() -> Any:
    """Import MSAL and translate missing dependency errors."""
    try:
        import msal  # type: ignore[import]
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            "msal is required to authenticate with Microsoft Graph."
        ) from exc
    return msal


class GraphClient:
    """Send email with Microsoft Graph using client credentials."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        *,
        scope: str = _DEFAULT_SCOPE,
        graph_base_url: str = _DEFAULT_GRAPH_BASE_URL,
        session: requests.Session | None = None,
        msal_app: Any | None = None,
        clock: Clock | None = None,
        token_refresh_buffer: timedelta | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_backoff_base: float = _DEFAULT_RETRY_BACKOFF_BASE,
        sleeper: Sleeper | None = None,
    ) -> None:
        """Initialize the Graph client."""
        if not tenant_id:
            raise GraphClientError("tenant_id is required for Graph client.")
        if not client_id:
            raise GraphClientError("client_id is required for Graph client.")
        if not client_secret:
            raise GraphClientError("client_secret is required for Graph client.")
        if max_retries < 0:
            raise GraphClientError("max_retries must be non-negative.")
        if timeout <= 0:
            raise GraphClientError("timeout must be positive.")
        if retry_backoff_base < 0:
            raise GraphClientError("retry_backoff_base must be non-negative.")
        refresh_buffer = (
            token_refresh_buffer
            if token_refresh_buffer is not None
            else _DEFAULT_TOKEN_REFRESH_BUFFER
        )
        if refresh_buffer.total_seconds() < 0:
            raise GraphClientError("token_refresh_buffer must be non-negative.")

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._graph_base_url = graph_base_url.rstrip("/")
        self._session = session or requests.Session()
        self._clock: Clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep: Sleeper = sleeper or time.sleep
        self._token_refresh_buffer = refresh_buffer
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff_base = retry_backoff_base
        self._msal_app = msal_app or self._build_msal_app()

        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None

    def send_mail(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        html_body: str,
        save_to_sent: bool = True,
    ) -> dict[str, Any]:
        """Send an HTML email through Microsoft Graph."""
        if not from_email:
            raise GraphClientError("from_email is required.")
        if not to_email:
            raise GraphClientError("to_email is required.")

        access_token = self._get_access_token()
        endpoint = (
            f"{self._graph_base_url}/v1.0/users/{quote(from_email, safe='')}/sendMail"
        )
        payload: dict[str, Any] = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body,
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_email}},
                ],
            },
            "saveToSentItems": save_to_sent,
        }
        headers = {"Authorization": f"Bearer {access_token}"}
        response = self._request_with_retry(
            "POST",
            endpoint,
            json=payload,
            headers=headers,
        )
        if 200 <= response.status_code < 300:
            payload_data = self._parse_json_response(response)
            metadata = self._request_metadata(response)
            if not payload_data:
                return metadata
            return {**payload_data, **metadata}
        self._raise_http_error(response)
        return {}

    def _build_msal_app(self) -> Any:
        msal = _load_msal()
        authority = f"https://login.microsoftonline.com/{self._tenant_id}"
        return msal.ConfidentialClientApplication(
            self._client_id,
            authority=authority,
            client_credential=self._client_secret,
        )

    def _get_access_token(self) -> str:
        now = self._now()
        if self._access_token and self._access_token_expires_at:
            if now + self._token_refresh_buffer < self._access_token_expires_at:
                return self._access_token

        token_response = self._acquire_token()
        access_token = token_response.get("access_token")
        if not access_token:
            self._raise_token_error(token_response)

        self._access_token = str(access_token)
        self._access_token_expires_at = self._resolve_expiration(token_response, now)
        return self._access_token

    def _acquire_token(self) -> Mapping[str, Any]:
        try:
            response = self._msal_app.acquire_token_for_client(scopes=[self._scope])
        except Exception as exc:
            message = self._redact_message("Token acquisition failed.")
            raise GraphClientError(message) from exc
        if not isinstance(response, Mapping):
            raise GraphClientError("Token acquisition failed with invalid response.")
        return response

    def _resolve_expiration(
        self,
        token_response: Mapping[str, Any],
        now: datetime,
    ) -> datetime:
        raw_expires_on = token_response.get("expires_on")
        if raw_expires_on is not None:
            try:
                return datetime.fromtimestamp(int(raw_expires_on), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                pass

        raw_expires_in = token_response.get("expires_in")
        if raw_expires_in is not None:
            try:
                return now + timedelta(seconds=int(raw_expires_in))
            except (TypeError, ValueError):
                pass

        return now + timedelta(minutes=30)

    def _raise_token_error(self, token_response: Mapping[str, Any]) -> None:
        error = token_response.get("error") or "unknown_error"
        description = token_response.get("error_description") or ""
        message = f"Token acquisition failed ({error})."
        if description:
            message = f"{message} {description}"
        raise GraphClientError(self._redact_message(message))

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        attempt = 0
        while True:
            try:
                response = self._session.request(
                    method,
                    url,
                    timeout=self._timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:
                message = self._redact_message(
                    "Graph request failed due to network error."
                )
                raise GraphClientError(message) from exc

            if self._should_retry(response.status_code) and attempt < self._max_retries:
                delay = self._retry_delay_seconds(response, attempt)
                self._sleep(delay)
                attempt += 1
                continue

            return response

    def _should_retry(self, status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code < 600

    def _retry_delay_seconds(self, response: requests.Response, attempt: int) -> float:
        retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after
        return self._retry_backoff_base * (2**attempt)

    def _parse_retry_after(self, value: str | None) -> float | None:
        if not value:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return max(float(stripped), 0.0)
        except ValueError:
            pass
        try:
            parsed = parsedate_to_datetime(stripped)
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = (parsed - self._now()).total_seconds()
        return max(delta, 0.0)

    def _parse_json_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            text = response.text or ""
        except Exception:
            return {}
        if not text.strip():
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {"raw": text}
        if isinstance(payload, dict):
            return payload
        return {"data": payload}

    def _request_metadata(self, response: requests.Response) -> dict[str, Any]:
        """Extract request identifiers and status code from a response."""
        return {
            "request_id": self._normalize_header_value(
                response.headers.get("request-id")
            ),
            "client_request_id": self._normalize_header_value(
                response.headers.get("client-request-id")
            ),
            "status_code": response.status_code,
        }

    def _normalize_header_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _raise_http_error(self, response: requests.Response) -> None:
        snippet = self._response_snippet(response)
        message = f"Graph API request failed with status {response.status_code}."
        if snippet:
            message = f"{message} Response: {snippet}"
        raise GraphClientError(self._redact_message(message))

    def _response_snippet(self, response: requests.Response) -> str:
        try:
            text = response.text or ""
        except Exception:
            return ""
        snippet = text.strip()
        if not snippet:
            return ""
        if len(snippet) > _RESPONSE_SNIPPET_LIMIT:
            snippet = f"{snippet[:_RESPONSE_SNIPPET_LIMIT]}..."
        return snippet

    def _redact_message(self, message: str) -> str:
        if not self._client_secret:
            return message
        return message.replace(self._client_secret, "***")

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise GraphClientError("Clock must return a timezone-aware datetime.")
        return now
