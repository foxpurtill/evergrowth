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

        # Presence events have their own decomposition path
        event_type = event.get("event", "")
        if event_type in ("presence.away", "presence.return"):
            return self._decompose_presence(event, ts, source_id, event_type)

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

    def _decompose_presence(self, event: dict, ts: float, source_id: str,
                             event_type: str) -> list[Trace]:
        """Decompose a presence.away or presence.return event."""
        presence_id = event.get("presence_id", "")
        reason = event.get("reason", "")
        is_away = event_type == "presence.away"
        label = "went away" if is_away else "returned"
        extra = f" ({reason})" if reason else ""

        return [
            Trace(
                trace_type=TraceType.EPISODIC,
                timestamp=ts,
                source_event_id=source_id,
                summary=f"Presence {label}{extra}",
                decay_curve=DecayCurve.FAST,
            ),
            Trace(
                trace_type=TraceType.RELATIONAL,
                timestamp=ts,
                source_event_id=source_id,
                summary=f"Self: {label}{extra}",
                decay_curve=DecayCurve.SLOW,
            ),
            Trace(
                trace_type=TraceType.TEMPORAL,
                timestamp=ts,
                source_event_id=source_id,
                summary=f"Presence event at session time",
                decay_curve=DecayCurve.MEDIUM,
            ),
        ]

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


class TraceReconstructor:
    """Reconstructs current context from stored traces.

    Takes a set of traces and builds a coherent picture of the current
    situation — not raw facts, but the shape of what's still relevant.
    """

    def reconstruct(self, traces: list[dict]) -> dict:
        """Build a context summary from a list of trace dicts."""
        if not traces:
            return {"summary": "No context available", "active_patterns": [], "active_entities": []}

        # Separate traces by type
        by_type: dict[str, list[dict]] = {}
        for t in traces:
            by_type.setdefault(t["trace_type"], []).append(t)

        # Build narrative from episodic traces
        narrative_parts = []
        for t in by_type.get("episodic", [])[-3:]:  # last 3
            narrative_parts.append(t["summary"])

        # Detect active emotional state
        emotional_state = None
        emotional_traces = by_type.get("emotional", [])
        if emotional_traces:
            latest = max(emotional_traces, key=lambda x: x.get("created_at", 0))
            val = latest.get("emotional_valence")
            if val is not None:
                if val > 0.3:
                    emotional_state = "positive"
                elif val < -0.3:
                    emotional_state = "challenging"
                else:
                    emotional_state = "neutral"

        # Collect active entities
        all_entities: set[str] = set()
        for t in by_type.get("relational", []):
            entities = t.get("entity_ids", [])
            if isinstance(entities, str):
                import json
                entities = json.loads(entities)
            all_entities.update(entities)

        # Collect active patterns (last 5)
        active_patterns = []
        for t in by_type.get("schematic", [])[-5:]:
            pid = t.get("pattern_id")
            if pid and pid not in active_patterns:
                active_patterns.append(pid)

        return {
            "summary": "; ".join(narrative_parts) if narrative_parts else "No recent activity",
            "emotional_state": emotional_state,
            "active_entities": sorted(all_entities),
            "active_patterns": active_patterns,
            "trace_count": len(traces),
        }
