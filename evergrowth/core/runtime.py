"""Core runtime for Evergrowth — the event loop that ties everything together."""

import asyncio
import logging
import signal

from .config import EvergrowthConfig, load_config

logger = logging.getLogger("evergrowth.runtime")


class EvergrowthRuntime:
    """
    The core runtime that orchestrates all Evergrowth components.

    Manages lifecycle of:
    - MCP server
    - Heartbeat engine
    - Memory engine
    - Skills system
    - Cron scheduler
    - Platform gateways
    """

    def __init__(self, config: EvergrowthConfig | None = None):
        self.config = config or load_config()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Components (initialized on start)
        self.memory = None
        self.skills = None
        self.heartbeat = None
        self.identity = None
        self.scheduler = None
        self.mcp_server = None
        self.tray = None
        self.window = None

    async def start(self):
        """Initialize and start all components."""
        logger.info(f"Evergrowth starting — DI: {self.config.di_name}")
        self._running = True

        # Ensure data directories exist
        data_dir = self.config.resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "skills").mkdir(exist_ok=True)
        (data_dir / "sessions").mkdir(exist_ok=True)
        (data_dir / "logs").mkdir(exist_ok=True)

        # Initialize components
        await self._init_memory()
        await self._init_identity()
        await self._init_skills()
        await self._init_heartbeat()
        await self._init_scheduler()
        await self._init_mcp()

        # Initialize UI if enabled
        if self.config.tray.enabled:
            self._init_tray()

        logger.info("Evergrowth started — all components initialized")

    async def stop(self):
        """Gracefully stop all components."""
        logger.info("Evergrowth stopping...")
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Shutdown UI first
        if self.tray:
            self.tray.stop()
        if self.window:
            self.window.stop()

        # Shutdown components in reverse order
        if self.mcp_server:
            await self.mcp_server.shutdown()
        if self.scheduler:
            await self.scheduler.shutdown()
        if self.heartbeat:
            self.heartbeat.stop()
        if self.memory:
            await self.memory.close()

        logger.info("Evergrowth stopped")

    async def _init_memory(self):
        """Initialize the memory engine."""
        from ..memory.engine import MemoryEngine
        self.memory = MemoryEngine(self.config)
        await self.memory.initialize()
        logger.info("Memory engine initialized")

    async def _init_identity(self):
        """Initialize the identity layer."""
        from ..identity.continuity import IdentityManager
        self.identity = IdentityManager(self.config)
        await self.identity.initialize()
        logger.info("Identity layer initialized")

    async def _init_skills(self):
        """Initialize the skills system."""
        from ..skills.registry import SkillRegistry
        self.skills = SkillRegistry(self.config)
        await self.skills.initialize()
        logger.info("Skills system initialized")

    async def _init_heartbeat(self):
        """Initialize the heartbeat engine."""
        from ..heartbeat.engine import HeartbeatEngine
        loop = asyncio.get_running_loop()
        self.heartbeat = HeartbeatEngine(
            self.config, self.memory, self.identity, loop=loop,
        )
        logger.info("Heartbeat engine initialized")

    async def _init_scheduler(self):
        """Initialize the cron scheduler."""
        from ..scheduler.cron import CronScheduler
        self.scheduler = CronScheduler(self.config)
        await self.scheduler.initialize()
        logger.info("Cron scheduler initialized")

    async def _init_mcp(self):
        """Initialize the MCP server."""
        from ..mcp.server import EvergrowthMCPServer
        self.mcp_server = EvergrowthMCPServer(
            self.config, self.memory, self.skills, self.identity, self.heartbeat, self.scheduler
        )
        logger.info("MCP server initialized")

    def _init_tray(self):
        """Initialize the system tray application."""
        try:
            from ..ui.tray import TrayApp
            self.tray = TrayApp(self)
            self.tray.start()
            logger.info("System tray initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize tray: {e}")

    async def run_forever(self):
        """Run until interrupted."""
        await self.start()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows doesn't support add_signal_handler for all signals
                pass

        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
