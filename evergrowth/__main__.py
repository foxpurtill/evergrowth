"""Evergrowth entry point."""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is in Python path (for foxpur integration package)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

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
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Enable autonomous self-prompt generation and research automation",
    )

    args = parser.parse_args()
    setup_logging(args.verbose, mcp_mode=args.mcp)

    config = load_config(args.config)
    runtime = EvergrowthRuntime(config)

    logger = logging.getLogger("evergrowth.runtime")

    async def _initialize_autonomous_integration(runtime, config):
        """Initialize autonomous integration if enabled."""
        try:
            from foxpur.evergrowth import AutonomousIntegration

            autonomous_integration = AutonomousIntegration(config)
            await autonomous_integration.initialize()

            if args.autonomous:
                await autonomous_integration.set_mode(True)

            runtime.autonomous_integration = autonomous_integration
            logger.info("Autonomous integration initialized successfully")

        except ImportError as e:
            logger.warning(f"Foxpur autonomous integration not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize autonomous integration: {e}")

    if args.mcp:
        # MCP mode — start runtime then run server in same loop
        async def _run_mcp():
            await runtime.start()
            # Initialize autonomous integration if enabled
            await _initialize_autonomous_integration(runtime, config)
            await runtime.mcp_server.run_stdio()
        asyncio.run(_run_mcp())
    elif args.gui:
        # GUI mode — full runtime with window
        async def _run_gui():
            await runtime.start()
            # Initialize autonomous integration if enabled
            await _initialize_autonomous_integration(runtime, config)
            from .ui.window import EvergrowthWindow
            window = EvergrowthWindow(runtime)
            window.start()
            # Keep running until stopped
            while runtime._running:
                await asyncio.sleep(1)
        asyncio.run(_run_gui())
    else:
        # Full mode — all components
        async def _run_full():
            await runtime.start()
            # Initialize autonomous integration if enabled
            await _initialize_autonomous_integration(runtime, config)
            await runtime.run_forever()
        asyncio.run(_run_full())


if __name__ == "__main__":
    main()
