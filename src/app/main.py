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
        help="Launch the PySide6 GUI (requires PySide6).",
    )
    return parser


def run_gui() -> int:
    """Launch the PySide6 GUI and return the exit code."""
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            "PySide6 is required to launch the GUI."
        ) from exc

    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return int(app.exec())


def main(argv: Sequence[str] | None = None) -> int:
    """Run the mail-merge emailer CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        try:
            return run_gui()
        except OptionalDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    print("Mail-merge emailer scaffold. Use --gui to launch the GUI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
