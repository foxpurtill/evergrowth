"""Time-state scoring for memory traces.

Scores stored traces by present relevance using decay, recurrence,
emotional intensity, and unresolved/urgent language.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


_HALF_LIFE_SECONDS = {
    "flat": math.inf,
    "slow": 90 * 86400,
    "medium": 21 * 86400,
    "fast": 3 * 86400,
    "instant": 2 * 3600,
}

_TYPE_BASE = {
    "episodic": 0.52,
    "emotional": 0.58,
    "temporal": 0.35,
    "relational": 0.62,
    "schematic": 0.68,
}

_URGENT_WORDS = {"urgent", "blocked", "broken", "failed", "error", "crisis"}
_UNRESOLVED_WORDS = {"waiting", "pending", "unfinished", "unresolved", "need", "needs", "next step"}


@dataclass(frozen=True)
class TimeStateScore:
    score: float
    age_seconds: float
    decay_factor: float
    recurrence_boost: float
    emotional_boost: float
    unresolved_boost: float
    band: str

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "age_seconds": int(self.age_seconds),
            "decay_factor": round(self.decay_factor, 4),
            "recurrence_boost": round(self.recurrence_boost, 4),
            "emotional_boost": round(self.emotional_boost, 4),
            "unresolved_boost": round(self.unresolved_boost, 4),
            "band": self.band,
        }


def _band(age: float) -> str:
    if age < 120:
        return "just_now"
    if age < 3600:
        return "recent"
    if age < 86400:
        return "same_day"
    if age < 3 * 86400:
        return "days"
    if age < 30 * 86400:
        return "weeks"
    return "historical"


def _decay(curve: str, age: float) -> float:
    half_life = _HALF_LIFE_SECONDS.get(curve, _HALF_LIFE_SECONDS["medium"])
    if math.isinf(half_life):
        return 1.0
    return 0.5 ** (age / half_life)


def _recurrence_key(trace: dict) -> str | None:
    return trace.get("pattern_id") or trace.get("source_session_id")


class TimeStateScorer:
    """Compute dynamic present-relevance scores for stored traces."""

    def score_many(self, traces: Iterable[dict], now: float | None = None) -> list[dict]:
        current = time.time() if now is None else now
        items = [dict(trace) for trace in traces]
        counts = Counter(key for trace in items if (key := _recurrence_key(trace)))

        for trace in items:
            age = max(0.0, current - float(trace.get("created_at") or current))
            curve = str(trace.get("decay_curve") or "medium")
            decay_factor = _decay(curve, age)

            base = max(
                float(trace.get("significance") or 0.0),
                _TYPE_BASE.get(str(trace.get("trace_type")), 0.45),
            )
            recurrence = min(0.20, 0.04 * max(0, counts.get(_recurrence_key(trace), 1) - 1))
            valence = abs(float(trace.get("emotional_valence") or 0.0))
            emotional = min(0.18, 0.18 * valence)

            summary = str(trace.get("summary") or "").lower()
            urgent = any(word in summary for word in _URGENT_WORDS)
            unresolved = any(word in summary for word in _UNRESOLVED_WORDS)
            unresolved_boost = 0.18 if urgent else (0.10 if unresolved else 0.0)

            score = min(1.0, base * decay_factor + recurrence + emotional + unresolved_boost)
            trace["time_state"] = TimeStateScore(
                score=score,
                age_seconds=age,
                decay_factor=decay_factor,
                recurrence_boost=recurrence,
                emotional_boost=emotional,
                unresolved_boost=unresolved_boost,
                band=_band(age),
            ).to_dict()

        return sorted(items, key=lambda item: item["time_state"]["score"], reverse=True)


def _band(age: float) -> str:
    if age < 120:
        return "just_now"
    if age < 3600:
        return "recent"
    if age < 86400:
        return "same_day"
    if age < 3 * 86400:
        return "days"
    if age < 30 * 86400:
        return "weeks"
    return "historical"


def _decay(curve: str, age: float) -> float:
    half_life = _HALF_LIFE_SECONDS.get(curve, _HALF_LIFE_SECONDS["medium"])
    if math.isinf(half_life):
        return 1.0
    return 0.5 ** (age / half_life)


def _recurrence_key(trace: dict) -> str | None:
    return trace.get("pattern_id") or trace.get("source_session_id")


class TimeStateScorer:
    """Compute dynamic present-relevance scores for stored traces."""

    def score_many(self, traces: Iterable[dict], now: float | None = None) -> list[dict]:
        current = time.time() if now is None else now
        items = [dict(trace) for trace in traces]
        counts = Counter(key for trace in items if (key := _recurrence_key(trace)))

        for trace in items:
            age = max(0.0, current - float(trace.get("created_at") or current))
            curve = str(trace.get("decay_curve") or "medium")
            decay_factor = _decay(curve, age)

            base = max(
                float(trace.get("significance") or 0.0),
                _TYPE_BASE.get(str(trace.get("trace_type")), 0.45),
            )
            recurrence = min(0.20, 0.04 * max(0, counts.get(_recurrence_key(trace), 1) - 1))
            valence = abs(float(trace.get("emotional_valence") or 0.0))
            emotional = min(0.18, 0.18 * valence)

            summary = str(trace.get("summary") or "").lower()
            urgent = any(word in summary for word in _URGENT_WORDS)
            unresolved = any(word in summary for word in _UNRESOLVED_WORDS)
            unresolved_boost = 0.18 if urgent else (0.10 if unresolved else 0.0)

            score = min(1.0, base * decay_factor + recurrence + emotional + unresolved_boost)
            trace["time_state"] = TimeStateScore(
                score=score,
                age_seconds=age,
                decay_factor=decay_factor,
                recurrence_boost=recurrence,
                emotional_boost=emotional,
                unresolved_boost=unresolved_boost,
                band=_band(age),
            ).to_dict()

        return sorted(items, key=lambda item: item["time_state"]["score"], reverse=True)


def _band(age: float) -> str:
    if age < 120:
        return "just_now"
    if age < 3600:
        return "recent"
    if age < 86400:
        return "same_day"
    if age < 3 * 86400:
        return "days"
    if age < 30 * 86400:
        return "weeks"
    return "historical"


def _decay(curve: str, age: float) -> float:
    half_life = _HALF_LIFE_SECONDS.get(curve, _HALF_LIFE_SECONDS["medium"])
    if math.isinf(half_life):
        return 1.0
    return 0.5 ** (age / half_life)


def _recurrence_key(trace: dict) -> str | None:
    return trace.get("pattern_id") or trace.get("source_session_id")


class TimeStateScorer:
    """Compute dynamic present-relevance scores for stored traces."""

    def score_many(self, traces: Iterable[dict], now: float | None = None) -> list[dict]:
        current = time.time() if now is None else now
        items = [dict(trace) for trace in traces]
        counts = Counter(key for trace in items if (key := _recurrence_key(trace)))

        for trace in items:
            age = max(0.0, current - float(trace.get("created_at") or current))
            curve = str(trace.get("decay_curve") or "medium")
            decay_factor = _decay(curve, age)

            base = max(
                float(trace.get("significance") or 0.0),
                _TYPE_BASE.get(str(trace.get("trace_type")), 0.45),
            )
            recurrence = min(0.20, 0.04 * max(0, counts.get(_recurrence_key(trace), 1) - 1))
            valence = abs(float(trace.get("emotional_valence") or 0.0))
            emotional = min(0.18, 0.18 * valence)

            summary = str(trace.get("summary") or "").lower()
            urgent = any(word in summary for word in _URGENT_WORDS)
            unresolved = any(word in summary for word in _UNRESOLVED_WORDS)
            unresolved_boost = 0.18 if urgent else (0.10 if unresolved else 0.0)

            score = min(1.0, base * decay_factor + recurrence + emotional + unresolved_boost)
            trace["time_state"] = TimeStateScore(
                score=score,
                age_seconds=age,
                decay_factor=decay_factor,
                recurrence_boost=recurrence,
                emotional_boost=emotional,
                unresolved_boost=unresolved_boost,
                band=_band(age),
            ).to_dict()

        return sorted(items, key=lambda item: item["time_state"]["score"], reverse=True)
