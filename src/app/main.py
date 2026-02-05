from __future__ import annotations

import argparse
import sys
from typing import Sequence

from app.core.errors import OptionalDependencyError


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the mail-merge emailer."""
    parser = argparse.ArgumentParser(
        prog="mail-merge-emailer",
        description="Mail-merge emailer scaffold.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the placeholder GUI (requires tkinter).",
    )
    return parser


def _launch_gui() -> None:
    """Launch a minimal placeholder GUI."""
    try:
        import tkinter as tk
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            "tkinter is required for the --gui option."
        ) from exc

    root = tk.Tk()
    root.title("Mail-merge emailer")
    root.geometry("420x240")

    label = tk.Label(
        root,
        text="Mail-merge emailer scaffold UI placeholder.",
        padx=20,
        pady=20,
    )
    label.pack()
    root.mainloop()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the mail-merge emailer CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        try:
            _launch_gui()
        except OptionalDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        print("Mail-merge emailer scaffold. Use --gui to launch the placeholder UI.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
