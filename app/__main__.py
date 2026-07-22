"""Enable ``python -m app`` as an alias for the CLI."""

from __future__ import annotations

import sys

from app.cli import main

if __name__ == "__main__":
    sys.exit(main())
