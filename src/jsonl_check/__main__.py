"""Entry point when running python -m jsonl_check."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
