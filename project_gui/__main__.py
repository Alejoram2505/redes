"""Launch the one-command project interface."""

from __future__ import annotations

import argparse

from .app import launch
from .controller import normalize_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Plant Energy MCP graphical presentation panel")
    parser.add_argument("--smoke-test", action="store_true", help="Validate imports without opening a window")
    args = parser.parse_args()
    if args.smoke_test:
        print(normalize_url("[https://plant-energy-mcp.onrender.com/mcp](https://plant-energy-mcp.onrender.com/mcp)"))
        print("GUI imports OK")
        return 0
    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
