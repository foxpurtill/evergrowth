"""Evergrowth entry point."""

import asyncio
import logging
import sys
from pathlib import Path

from .core.config import load_config
from .core.runtime import EvergrowthRuntime


def setup_logging(verbose: bool = False, mcp_mode: bool = False):
    """Configure logging for Evergrowth.
    In MCP mode, logs go to stderr to avoid corrupting stdio JSON communication.
    """
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path.home() / ".evergrowth" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stderr if mcp_mode else sys.stdout),
        logging.FileHandler(log_dir / "evergrowth.log", encoding="utf-8"),
    ]

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
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
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Run with GUI window (full mode)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose, mcp_mode=args.mcp)

    config = load_config(args.config)
    runtime = EvergrowthRuntime(config)

<<<<<<< HEAD
=======
    logger = logging.getLogger("evergrowth.runtime")

>>>>>>> 4dda864 (Merge autonomous brain into self-prompt engine: research + skill intents, remove foxpur package)
    if args.mcp:
        async def _run_mcp():
            await runtime.start()
            await runtime.mcp_server.run_stdio()
        asyncio.run(_run_mcp())
    elif args.gui:
        async def _run_gui():
            await runtime.start()
            from .ui.window import EvergrowthWindow
            window = EvergrowthWindow(runtime)
            window.start()
            while runtime._running:
                await asyncio.sleep(1)
        asyncio.run(_run_gui())
    else:
<<<<<<< HEAD
        # Full mode — all components
        asyncio.run(runtime.run_forever())
=======
        async def _run_full():
            await runtime.start()
            await runtime.run_forever()
        asyncio.run(_run_full())
>>>>>>> 4dda864 (Merge autonomous brain into self-prompt engine: research + skill intents, remove foxpur package)


if __name__ == "__main__":
    main()
