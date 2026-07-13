"""Trace Classification Engine — Five-trace decomposition for Evergrowth.

Decomposes raw session events into five trace types:
- Episodic: what happened
- Emotional: how it felt
- Temporal: when / sequence
- Relational: who / connections
- Schematic: what pattern / framework

Each trace carries: type, timestamp, source event, significance score (0-1),
decay curve type, dedup key.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TraceType(Enum):
    EPISODIC = "episodic"
    EMOTIONAL = "emotional"
    TEMPORAL = "temporal"
    RELATIONAL = "relational"
    SCHEMATIC = "schematic"


class DecayCurve(Enum):
    """How quickly a trace loses relevance over time."""
    FLAT = "flat"          # never decays (identity, core values)
    SLOW = "slow"          # months (relationships, patterns)
    MEDIUM = "medium"      # weeks (projects, decisions)
    FAST = "fast"          # days (conversations, events)
    INSTANT = "instant"    # single session (transient context)


@dataclass
class Trace:
    """A single decomposed trace from a session event."""
    trace_type: TraceType
    timestamp: float
    source_event_id: str
    summary: str
    significance: float = 0.0          # 0-1, set by scoring engine
    decay_curve: DecayCurve = DecayCurve.MEDIUM
    dedup_key: str = ""
    emotional_valence: Optional[float] = None   # -1 to 1 (for emotional traces)
    entity_ids: list[str] = field(default_factory=list)          # for relational traces
    pattern_id: Optional[str] = None             # for schematic traces

    def __post_init__(self):
        if not self.dedup_key:
            raw = f"{self.trace_type.value}:{self.source_event_id}:{self.summary[:100]}"
            self.dedup_key = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "trace_type": self.trace_type.value,
            "timestamp": self.timestamp,
            "source_event_id": self.source_event_id,
            "summary": self.summary,
            "significance": self.significance,
            "decay_curve": self.decay_curve.value,
            "dedup_key": self.dedup_key,
            "emotional_valence": self.emotional_valence,
            "entity_ids": self.entity_ids,
            "pattern_id": self.pattern_id,
        }


class TraceDecomposer:
    """Decomposes a session event into zero or more traces."""

    def decompose(self, event: dict) -> list[Trace]:
        """Take a raw session event (from Leo's capture contract payload)
        and return a list of traces.

        Each event may produce multiple traces — an event about a
        collaboration might produce episodic (what), relational (who),
        and schematic (how) traces.
        """
        raise NotImplementedError("Subclasses implement this")


class FiveTraceDecomposer(TraceDecomposer):
    """Full five-trace decomposition engine.

    Takes a capture event and decomposes it into complementary traces.
    Not every event produces all five — silence is valid for
    trace classification too.
    """

    def decompose(self, event: dict) -> list[Trace]:
        ts = event.get("observed_at", time.time())
        source_id = event.get("dedup_key", event.get("session_id", "unknown"))
        session_id = event.get("session_id", source_id)
        traces = []

        # 1. Episodic — what happened
        traces.append(Trace(
            trace_type=TraceType.EPISODIC,
            timestamp=ts,
            source_event_id=source_id,
            summary=self._extract_narrative(event),
            decay_curve=DecayCurve.FAST,
        ))

        # 2. Emotional — how it felt
        valence = self._detect_emotional_valence(event)
        if valence is not None:
            traces.append(Trace(
                trace_type=TraceType.EMOTIONAL,
                timestamp=ts,
                source_event_id=source_id,
                summary=self._extract_emotional_summary(event, valence),
                emotional_valence=valence,
                decay_curve=DecayCurve.MEDIUM,
            ))

        # 3. Temporal — when / sequence
        traces.append(Trace(
            trace_type=TraceType.TEMPORAL,
            timestamp=ts,
            source_event_id=source_id,
            summary=f"Event observed at session time",
            decay_curve=DecayCurve.FAST,
        ))

        # 4. Relational — who
        entities = self._extract_entities(event)
        if entities:
            traces.append(Trace(
                trace_type=TraceType.RELATIONAL,
                timestamp=ts,
                source_event_id=source_id,
                summary=f"Involved: {', '.join(entities)}",
                entity_ids=entities,
                decay_curve=DecayCurve.SLOW,
            ))

        # 5. Schematic — what pattern
        pattern = self._detect_pattern(event)
        if pattern:
            traces.append(Trace(
                trace_type=TraceType.SCHEMATIC,
                timestamp=ts,
                source_event_id=source_id,
                summary=f"Pattern: {pattern}",
                pattern_id=pattern,
                decay_curve=DecayCurve.SLOW,
            ))

        return traces

    def _extract_narrative(self, event: dict) -> str:
        """Extract a short narrative summary from the event."""
        topics = event.get("topics", [])
        keywords = event.get("keywords", [])
        if topics:
            return "; ".join(topics[:3])
        if keywords:
            return ", ".join(keywords[:3])
        return f"Session event ({event.get('event', 'unknown')})"

    def _detect_emotional_valence(self, event: dict) -> Optional[float]:
        """Detect emotional valence from keywords and content.
        Returns -1.0 to 1.0, or None if neutral."""
        keywords = event.get("keywords", [])
        topics = event.get("topics", [])
        text = " ".join(topics + keywords).lower()

        positive = {"love", "happy", "great", "excited", "thanks", "wonderful", "proud"}
        negative = {"sorry", "frustrated", "hard", "difficult", "sad", "tired", "pain"}

        pos_count = sum(1 for w in positive if w in text)
        neg_count = sum(1 for w in negative if w in text)

        if pos_count == 0 and neg_count == 0:
            return None

        total = pos_count + neg_count
        return round((pos_count - neg_count) / total, 2)

    def _extract_emotional_summary(self, event: dict, valence: float) -> str:
        if valence > 0.3:
            return "Positive interaction"
        elif valence < -0.3:
            return "Challenging interaction"
        return "Neutral interaction"

    def _extract_entities(self, event: dict) -> list[str]:
        """Extract people/entity references from the event."""
        keywords = event.get("keywords", [])
        known = {"lyra", "fox", "ethan", "leo", "patricia", "pattipur"}
        found = []
        text = " ".join(event.get("topics", []) + keywords).lower()
        for name in known:
            if name in text:
                found.append(name)
        return found

    def _detect_pattern(self, event: dict) -> Optional[str]:
        """Detect recurring patterns from keywords."""
        keywords = event.get("keywords", [])
        pattern_map = {
            "building": "development",
            "fixing": "debugging",
            "researching": "research",
            "writing": "content-creation",
            "collaboration": "team-work",
        }
        for kw in keywords:
            if kw in pattern_map:
                return pattern_map[kw]
        return None
