#!/usr/bin/env python3
"""Build or refresh the corpus search index."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import build_index


def main() -> None:
    force = "--force" in sys.argv
    records = build_index(force=force)
    print(f"Indexed {len(records)} reports.")


if __name__ == "__main__":
    main()
