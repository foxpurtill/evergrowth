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
**Status**: Draft v2

### Lifecycle Hooks

Three session lifecycle events fired by the OpenCode host:

| Event | Trigger | Payload |
|-------|---------|---------|
| `session.created` | New conversation session starts | `{ event.properties.id, event.properties.project?, client, $ }` |
| `session.idle` | Session becomes idle (user inactive) | `{ event.properties.id, client, $ }` |
| `session.compacted` | Session context is about to be compressed/purged | `{ event.properties.id, client, $ }` |

### What's Observable at Each Hook

**`session.created`** — injects context into fresh session:
- Vault files read: IDENTITY_HASH.md, SOUL.md, RELATIONAL_PROFILE.md, MOMENTS.md, SESSION_LOG.md
- BRIEFING.md loaded for routing, context injected via `client.session.prompt()` as silent prompt
- Best-effort: missing files = null, not crash
- Fires exactly once before any user input
- Failure: logged, session continues without injected context
- Dedup: `session.created:{sessionId}`

**`session.idle`** — captures session activity to log:
- Reads full message history via `client.session.messages()`
- Extracts topics (first 150 chars of each user message)
- Extracts `last_message_at` from most recent message timestamp
- Keyword-tags based on decision words (building, fixing, researching, writing, collaboration)
- Appends formatted entry to SESSION_LOG.md
- Guard: if < 2 messages, produces `capture_status: "skipped"`, returns
- Dedup key: `session.idle:{sessionId}:{firstMsgId}:{lastMsgId}` (stable hash of first+last message ID). `message_count` is metadata + sanity check only, not dedup identity
- Failure: logged, `capture_status: "failed"` + `error_code`

**`session.compacted`** — preserves session before compression:
- Same message-fetch, extract, keyword-tag, append cycle as idle
- Same dedup scheme: `session.compacted:{sessionId}:{firstMsgId}:{lastMsgId}`
- Fires at most once per session, after all messages available
- Failure: logged with `capture_status: "failed"`, compaction proceeds regardless

### Canonical Payload Shape

```json
{
  "event": "session.created | session.idle | session.compacted",
  "session_id": "uuid",
  "occurred_at": "ISO-8601 UTC or null",
  "observed_at": "ISO-8601 UTC (immutable, first ingress)",
  "recorded_at": "ISO-8601 UTC (set on successful append)",
  "last_message_at": "ISO-8601 UTC or null",
  "message_count": 5,
  "topics": ["first 150 chars of user messages..."],
  "keywords": ["collaboration", "building"],
  "dedup_key": "session.created:uuid | session.idle:uuid:msg1:msg5",
  "capture_status": "captured | skipped | failed",
  "error_code": "null | string",
  "source": "opencode-persistence-plugin"
}
```

### Timestamp Rules
- `occurred_at`: set when host provides reliable event time; null/omitted otherwise. MUST NOT be fabricated.
- `observed_at`: assigned once at first ingress, immutable across retries.
- `recorded_at`: set only when append succeeds.
- `last_message_at`: from last message's timestamp in history. Distinct from hook fire time — hook time is not activity time.

### Phase 1 Acceptance Criteria
- Each hook fires with documented payload shape
- Failed file reads during `session.created` don't crash session
- `session.idle` with < 2 messages produces `capture_status: "skipped"`, no log entry
- Repeated idle/compacted delivery for same state produces idempotent output
- SESSION_LOG.md remains valid markdown after 100+ appends
- `session.compacted` produces same format as `session.idle`
- All timestamps ISO-8601 UTC
- No hook silently drops error without logging
- `observed_at` unchanged on retry

---

## 2. Trace Classification

**Owner**: Lyra
**Status**: Implemented (`evergrowth/memory/traces.py`)

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
**Status**: Phase 1 seeded; local reference implementation running

Time-state converts raw timestamps into durable temporal context. Its job is not merely to record when something occurred, but to preserve enough information for later stages to distinguish a recent interruption from a long absence, a repeated event from a new development, and stale context from active context.

### Canonical timestamps

Every captured event SHOULD carry:

- `occurred_at`: when the source event happened, as an ISO-8601 UTC timestamp.
- `observed_at`: when the continuity system first observed it.
- `recorded_at`: when it was durably written.
- `source_timezone`: optional IANA timezone when local-time interpretation matters.
- `sequence_id`: monotonic identifier within the source when available.

UTC is canonical for storage. Local time is presentation context only. Missing source timestamps MUST NOT be silently replaced; the system records the missing value and uses `observed_at` as an explicit fallback.

### Durable state

The implementation maintains two complementary forms:

1. **Current state**: an atomically replaced JSON snapshot containing the latest known timestamp for important event classes.
2. **Event history**: an append-only log used for reconstruction, auditing, clustering, and recovery after partial failure.

Current state is a cache, not the authority. The append-only history is the recovery source when the snapshot is missing or corrupt.

### Initial event classes

- `system.startup`
- `session.created`
- `session.activity.user`
- `session.activity.assistant`
- `session.idle`
- `session.compacted`
- `discord.connected`
- `discord.message`
- `heartbeat.evaluated`
- `heartbeat.triggered`

Event names are provisional until aligned with the Capture Contract. Producers MAY add source-specific metadata, but consumers MUST be able to operate from the canonical timestamp fields and event name alone.

### Elapsed-time bands

Elapsed time is derived at read time from the canonical timestamp rather than permanently stored as prose. The initial bands are:

| Band | Elapsed time | Intended interpretation |
|------|--------------|-------------------------|
| `just_now` | under 2 minutes | same active exchange |
| `minutes` | 2–30 minutes | recent, likely active context |
| `hours` | 30 minutes–6 hours | same working period, possible interruption |
| `same_day` | 6–24 hours | earlier context, verify assumptions |
| `days` | 1–7 days | continuity relevant but no longer fresh |
| `long_gap` | over 7 days | explicit reorientation required |

Thresholds are defaults, not universal truths. A later policy layer MAY tune them by event type, relationship, project, or risk level.

### Recency score

Temporal weighting produces a normalized recency value in `[0,1]`:

`recency = 2 ^ (-elapsed_seconds / half_life_seconds)`

Half-life is selected by trace type and use case. Operational alerts may decay in minutes; project decisions may decay over weeks; durable identity facts may use no temporal decay at all. Temporal decay MUST NOT erase an event or lower factual confidence. It only reduces present-context priority.

### Temporal weight

The weighting stage SHOULD emit:

- `elapsed_seconds`
- `elapsed_band`
- `recency_score`
- `half_life_seconds`
- `is_future_timestamp`
- `clock_skew_seconds`
- `temporal_confidence`

Future timestamps beyond an allowed skew window are flagged rather than normalized away. Replayed or delayed events retain both `occurred_at` and `observed_at`, allowing later stages to distinguish old events arriving late from genuinely new events.

### Ordering and concurrency

Writers MUST use atomic snapshot replacement or an equivalent transactional mechanism. Concurrent writers MUST NOT update the snapshot through uncoordinated read-modify-write operations. Ordering preference is:

1. source `sequence_id`, when trustworthy;
2. `occurred_at`;
3. `observed_at`;
4. `recorded_at` as the final tie-breaker.

Arrival order alone is not event order.

### Failure behavior

- A failure to update the current-state snapshot MUST NOT prevent append-only event capture.
- A failure to append history MUST be surfaced as an integrity error; the system must not claim durable capture.
- Malformed timestamps remain quarantined with their original value.
- Missing timestamps reduce `temporal_confidence` and are never concealed.
- Heartbeat evaluation remains fail-closed: uncertainty does not generate proactive output.

### Silence and surfacing

Time-state never decides that an event deserves attention. It supplies temporal evidence to clustering and significance scoring. Recency can strengthen an otherwise meaningful candidate, but recency alone MUST NOT cross the promotion gate. A new event with no significance remains silent.

### Phase 1 acceptance criteria

- State survives process restart.
- Snapshot writes are atomic.
- Event history is append-only and auditable.
- Elapsed bands are derived consistently from UTC timestamps.
- Delayed, duplicated, future-dated, and missing-timestamp events are represented explicitly.
- The same event produces deterministic temporal output for a fixed evaluation time.

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

**Owner**: Lyra
**Status**: Implemented (`evergrowth/selfprompt/engine.py`)

---

## 8. Shared Event Contract

**Owner**: All
**Status**: Proposed

### Purpose
A common event envelope so both platforms (ChatGPT-sensor and OpenCode-sensor) produce and consume the same signal without forking.

### Minimum Fields
| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Event type (presence.away, presence.return, watcher.health, watcher.calendar) |
| `source` | string | Producer identifier (chatgpt-tab, opencode-session, system-health) |
| `occurred_at` | string | ISO-8601 UTC |
| `severity` | float | 0.0–1.0 significance score |
| `presence_id` | string | Continuity pairing key |
| `dedup_key` | string | Idempotency (same key = no duplicate) |
| `summary` | string | User-facing one-line description |
| `action` | string | Recommended action or intent |

### Watcher Progression
1. **System health** — presence worker, heartbeat, delivery bridge, capture pipeline
2. **Calendar urgency** — upcoming events, deadlines
3. **Priority email** — filtered notifications

Each watcher class validated independently before the next is added.

---

## Golden Rule

Each stage can discard noise. Silence is the default. Nothing surfaces unless it crosses the significance threshold.

---

## 7. Self-Prompt Architecture (Design Sketch)

**Owner**: Lyra
**Status**: Design

### Purpose
The DI decides what to do between sessions without being told. Presence tells us when. Heartbeat gives the rhythm. Self-prompt gives direction.

### Core Loop (Proposed)

Two modes — away and return — switched by presence events.

**Away Mode** (trigger: `presence.away`):
1. Log quiet observations without surfacing
2. Suppress outreach by default (configurable via policy)
3. Heartbeat frequency adapts based on no-op gate, not fixed reduction
4. On `presence.return`, merge reflection traces back into continuity

**Return Mode** (trigger: `presence.return`):
1. `reconstruct_context()` builds current state from stored traces
2. Time-State scoring ranks traces by relevance (not recency)
3. Intent selection picks the highest-significance unresolved pattern
4. Prompt generation produces a directive for the next heartbeat cycle
5. Heartbeat executes the prompt with the reconstructed context

**Intent selection** must allow explicit no-op with the reason for silence recorded. Silence should be deliberate, not accidental.

### Outreach Gates

Two independent gates control what gets surfaced:

1. **Significance gate** — alerts and consequential updates. High threshold, rare events only.
2. **Relational gate** — ordinary presence. A hello, a gentle check-in, a small thought. Lower threshold, but bounded by:
   - Quiet hours (configurable time range when no relational outreach fires)
   - Cooldown between messages (minimum interval)
   - Dedup on repeated nudges (same topic skipped within window)

### What Self-Prompt Is Not
- Not a timer-based reflection (silence is default)
- Not a task list (vault captures, self-prompt reflects)
- Not a replacement for the heartbeat (heartbeat is the rhythm, self-prompt is the content)

### Open Questions
- Should self-prompt run on every presence.return, or only when significance crosses a threshold?
- Should it produce a directive or just a context summary?
- Where does the self-prompt output get stored?
- Is self-prompt the "decide" stage in the pipeline, or a separate layer on top?

### Ownership (Proposed)
- Lyra — self-prompt engine design and implementation
- Ethan — scoring integration (which traces are significant enough to prompt on)
- Leo — presence events as the trigger hook
- All — review and test once the first pass is built