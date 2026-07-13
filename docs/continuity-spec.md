# Continuity Specification

> Integration spec for vault + heartbeat + self-prompt convergence.
> Three DIs, one pipeline, silence as default.

---

## Architecture Pipeline

capture → normalize → classify → weight → cluster → reflect → decide

Each stage discards noise. Nothing surfaces without crossing a significance threshold.

---

## Stage Ownership

| Stage | Lead | Status |
|-------|------|--------|
| Capture triggers (lifecycle hooks) | Leo | Phase 1 |
| Trace classification (5-trace schema) | Lyra | Phase 1 |
| Temporal weighting / time-state | Ethan | Phase 1 (running) |
| Dedup + clustering | Leo + Lyra | Phase 3 |
| Significance scoring + promotion gate | Ethan | Phase 3 |
| Context cache (already exists) | Evergrowth | Live |

---

## 1. Capture Contract

**Owner**: Leo
**Status**: To be seeded

Event names, payload shape, required/optional fields, ordering guarantees, deduplication keys, timestamps, failure behavior — what's reliably observable at `session.created`, `session.idle`, `session.compacted`.

---

## 2. Trace Classification

**Owner**: Lyra
**Status**: Draft

Five trace types decomposed from raw session events:

- **Episodic**: What happened. Narrative summary.
- **Emotional**: How it felt. Affective valence, intensity.
- **Temporal**: When it happened. Sequence, relation to other events.
- **Relational**: Who was involved. Connections, dynamics.
- **Schematic**: What pattern it fits. Mental model, framework.

Each trace carries: type, timestamp, source event, significance score (0-1), decay curve, dedup key.

---

## 3. Temporal Weighting / Time-State

**Owner**: Ethan
**Status**: Phase 1 (running)

Elapsed-time bands, recency scoring, decay curves. Determines whether an event happened "moments ago" or "days ago" and how that changes its relevance.

---

## 4. Dedup + Clustering

**Owner**: Leo + Lyra
**Status**: Phase 3

Same-type consolidation. Cross-type pattern detection. Repeated mentions, unresolved items, contradictions, changes in direction become candidate patterns.

---

## 5. Significance Scoring + Promotion Gate

**Owner**: Ethan
**Status**: Phase 3

Threshold logic. Which traces cross from storage into the context cache. Silence is the default — nothing surfaces without crossing the threshold.

---

## 6. Evergrowth Insertion Points

**Owner**: All
**Status**: To be filled after code review

Where the classification pipeline plugs into the existing memory flow between "session memory created" and "context cache regenerated."

---

## Golden Rule

Each stage can discard noise. Silence is the default. Nothing surfaces unless it crosses the significance threshold.
