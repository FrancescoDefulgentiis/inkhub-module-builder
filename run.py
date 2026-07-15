"""Entry point for the InkHub Module Builder.

Run this file (``python run.py``) to launch the local Flask web app.
Then open http://localhost:5001 in your browser.
"""

from __future__ import annotations

import sys

from backend.server import create_app, DEFAULT_HOST, DEFAULT_PORT


def main(argv: list[str] | None = None) -> int:
    app = create_app()
    app.run(host=DEFAULT_HOST, port=DEFAULT_PORT, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
