"""Mocked tests for the Microsoft Graph client."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import pytest
import requests

from app.core.errors import GraphClientError
from app.core.graph_client import GraphClient


class DummyMsalApp:
    """Stub MSAL app for tests."""

    def __init__(self, access_token: str = "token", expires_in: int = 3600) -> None:
        self.access_token = access_token
        self.expires_in = expires_in
        self.scopes: list[str] | None = None

    def acquire_token_for_client(self, scopes: list[str]) -> dict[str, Any]:
        self.scopes = scopes
        return {"access_token": self.access_token, "expires_in": self.expires_in}


class DummySession:
    """Session stub that returns queued responses."""

    def __init__(self, responses: list[requests.Response]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self._responses:
            raise AssertionError("No responses left in queue.")
        return self._responses.pop(0)


def fixed_clock() -> datetime:
    """Return a deterministic, timezone-aware timestamp."""
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_response(
    status_code: int,
    *,
    json_body: dict[str, Any] | None = None,
    text_body: str | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """Create a mocked requests.Response object."""
    response = requests.Response()
    response.status_code = status_code
    response.headers = headers or {}
    response.url = "https://graph.microsoft.com/v1.0/users/test/sendMail"
    if json_body is not None:
        response._content = json.dumps(json_body).encode("utf-8")
        response.headers.setdefault("Content-Type", "application/json")
    elif text_body is not None:
        response._content = text_body.encode("utf-8")
    else:
        response._content = b""
    response.encoding = "utf-8"
    return response


def test_send_mail_success_includes_authorization_header() -> None:
    session = DummySession(
        [
            make_response(
                202,
                headers={"request-id": "req-123", "client-request-id": "client-456"},
            )
        ]
    )
    client = GraphClient(
        "tenant",
        "client",
        "secret",
        session=session,
        msal_app=DummyMsalApp(access_token="token-123"),
        clock=fixed_clock,
        sleeper=lambda _: None,
    )

    result = client.send_mail(
        "sender@example.com",
        "to@example.com",
        "Hello",
        "<p>Body</p>",
    )

    assert result == {
        "request_id": "req-123",
        "client_request_id": "client-456",
        "status_code": 202,
    }
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["headers"]["Authorization"] == "Bearer token-123"
    assert call["url"].endswith("/v1.0/users/sender%40example.com/sendMail")
    payload = call["json"]
    assert payload["saveToSentItems"] is True
    assert payload["message"]["subject"] == "Hello"


def test_send_mail_success_merges_payload_and_metadata() -> None:
    session = DummySession(
        [
            make_response(
                202,
                json_body={"id": "message-123"},
                headers={"request-id": "req-999", "client-request-id": "client-999"},
            )
        ]
    )
    client = GraphClient(
        "tenant",
        "client",
        "secret",
        session=session,
        msal_app=DummyMsalApp(access_token="token-123"),
        clock=fixed_clock,
        sleeper=lambda _: None,
    )

    result = client.send_mail(
        "sender@example.com",
        "to@example.com",
        "Hello",
        "<p>Body</p>",
    )

    assert result["id"] == "message-123"
    assert result["request_id"] == "req-999"
    assert result["client_request_id"] == "client-999"
    assert result["status_code"] == 202


def test_send_mail_retries_on_429_then_succeeds() -> None:
    session = DummySession(
        [
            make_response(429, text_body="busy", headers={"Retry-After": "0"}),
            make_response(202, headers={"request-id": "req-789"}),
        ]
    )
    sleeper_calls: list[float] = []

    def sleeper(seconds: float) -> None:
        sleeper_calls.append(seconds)

    client = GraphClient(
        "tenant",
        "client",
        "secret",
        session=session,
        msal_app=DummyMsalApp(),
        clock=fixed_clock,
        max_retries=1,
        sleeper=sleeper,
    )

    result = client.send_mail(
        "sender@example.com",
        "to@example.com",
        "Hello",
        "<p>Body</p>",
    )

    assert result["status_code"] == 202
    assert result["request_id"] == "req-789"
    assert result["client_request_id"] is None
    assert len(session.calls) == 2
    assert len(sleeper_calls) == 1


def test_retry_delay_applies_jitter_when_no_retry_after() -> None:
    response = make_response(503, text_body="service unavailable")
    jitter_values = iter([0.9, 1.1])

    def jitter(delay: float) -> float:
        return delay * next(jitter_values)

    client = GraphClient(
        "tenant",
        "client",
        "secret",
        session=DummySession([]),
        msal_app=DummyMsalApp(),
        clock=fixed_clock,
        retry_backoff_base=1.0,
        retry_jitter=jitter,
        sleeper=lambda _: None,
    )

    first_delay = client._retry_delay_seconds(response, 0)
    second_delay = client._retry_delay_seconds(response, 0)

    assert first_delay == pytest.approx(0.9)
    assert second_delay == pytest.approx(1.1)
    assert first_delay != second_delay


def test_retry_delay_honors_retry_after_without_jitter() -> None:
    response = make_response(
        503,
        text_body="service unavailable",
        headers={"Retry-After": "3"},
    )

    def jitter(_: float) -> float:
        raise AssertionError("jitter should not run when Retry-After is set")

    client = GraphClient(
        "tenant",
        "client",
        "secret",
        session=DummySession([]),
        msal_app=DummyMsalApp(),
        clock=fixed_clock,
        retry_jitter=jitter,
        sleeper=lambda _: None,
    )

    assert client._retry_delay_seconds(response, 0) == 3.0


def test_send_mail_raises_on_400_without_retry() -> None:
    session = DummySession([make_response(400, text_body="bad request")])
    client = GraphClient(
        "tenant",
        "client",
        "secret",
        session=session,
        msal_app=DummyMsalApp(),
        clock=fixed_clock,
        max_retries=2,
        sleeper=lambda _: None,
    )

    with pytest.raises(GraphClientError) as exc:
        client.send_mail(
            "sender@example.com",
            "to@example.com",
            "Hello",
            "<p>Body</p>",
        )

    assert "status 400" in str(exc.value)
    assert "bad request" in str(exc.value)
    assert len(session.calls) == 1
