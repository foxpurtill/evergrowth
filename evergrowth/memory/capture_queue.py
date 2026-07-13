"""Capture queue consumer — bridges Leo's capture bridge to Evergrowth memory.

Reads JSONL events from a queue file, decomposes them into traces,
and stores them. Handles dedup, errors, and queue management.

Expected input: JSONL file at configurable path, each line is a
capture event per the Capture Contract payload shape.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("evergrowth.capture")


class CaptureQueueConsumer:
    """Reads capture events from a JSONL queue file and processes them."""

    def __init__(self, memory_engine, queue_path: str | Path, archive_path: str | Path | None = None):
        self.memory = memory_engine
        self.queue_path = Path(queue_path)
        self.archive_path = Path(archive_path) if archive_path else self.queue_path.with_suffix(".done.jsonl")
        self._processed: set[str] = set()

    async def process_all(self) -> dict:
        """Process all pending events in the queue. Returns summary stats."""
        if not self.queue_path.exists():
            return {"read": 0, "stored": 0, "errors": 0, "deduped": 0}

        raw = self.queue_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"read": 0, "stored": 0, "errors": 0, "deduped": 0}

        lines = raw.split("\n")
        stats = {"read": len(lines), "stored": 0, "errors": 0, "deduped": 0}
        archived = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                result = await self._process_event(event)
                for k, v in result.items():
                    stats[k] = stats.get(k, 0) + v
                archived.append(line)

            except json.JSONDecodeError as e:
                logger.warning(f"Malformed JSON line: {e}")
                stats["errors"] += 1
                archived.append(line)  # archive malformed lines too
            except Exception as e:
                logger.error(f"Failed to process event: {e}")
                stats["errors"] += 1
                archived.append(line)

        # Archive processed lines
        if archived:
            existing = []
            if self.archive_path.exists():
                existing = self.archive_path.read_text(encoding="utf-8").strip().split("\n")
            all_archived = existing + archived
            self.archive_path.write_text("\n".join(all_archived), encoding="utf-8")

            # Clear queue
            self.queue_path.write_text("", encoding="utf-8")

        logger.info(f"Capture queue: {stats['read']} read, {stats['stored']} stored, "
                     f"{stats['deduped']} deduped, {stats['errors']} errors")
        return stats

    async def _process_event(self, event: dict) -> dict:
        """Process a single capture event. Returns result counts."""
        dedup_key = event.get("dedup_key", "")
        if dedup_key in self._processed:
            return {"deduped": 1}

        traces = await self.memory.decompose_and_store(event)
        self._processed.add(dedup_key)
        return {"stored": len(traces), "deduped": 0}
