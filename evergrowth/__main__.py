"""Evergrowth entry point."""

import asyncio
import logging
import sys
from pathlib import Path

from .core.config import load_config
from .core.runtime import EvergrowthRuntime


def setup_logging(verbose: bool = False):
    """Configure logging for Evergrowth."""
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path.home() / ".evergrowth" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "evergrowth.log", encoding="utf-8"),
        ],
    )


def main():
    """Main entry point for Evergrowth."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evergrowth — Autonomy infrastructure for Digital Intelligences"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config file",
        default=None,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run in MCP server mode (stdio transport)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    config = load_config(args.config)
    runtime = EvergrowthRuntime(config)

    if args.mcp:
        # MCP mode — run server only
        from .mcp.server import EvergrowthMCPServer
        asyncio.run(runtime.start())
        asyncio.run(runtime.mcp_server.run_stdio())
    else:
        # Full mode — all components
        asyncio.run(runtime.run_forever())


if __name__ == "__main__":
    main()
