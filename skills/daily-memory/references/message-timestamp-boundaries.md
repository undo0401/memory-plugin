# Message-timestamp boundaries for memory snapshots

Use this note when `MEMORY_EMOTIONS_CONTEXT.md` or related snapshots appear to pull messages from the wrong operational day.

## Durable lessons

- Prefer addon-side fixes for memory snapshot issues; avoid modifying Hermes core when the problem can be absorbed in `/opt/data/scripts/diaries/` and plugin consumers.
- Preserve message-level raw timestamps end-to-end in snapshot payloads. Display strings like `time: YYYY-MM-DD HH:MM` are not enough as the authoritative comparison source.
- Distinguish three different times during debugging:
  1. `message timestamp` — when the message was actually sent
  2. `generated_at` — when the snapshot file was built
  3. `generated_operational_day` — which 4:00-bounded day the snapshot considered to be “today”

## Recommended payload fields

In collector output, keep all three when possible:

- `time` — human-readable display time
- `timestamp_iso` — exact timezone-aware ISO timestamp
- `timestamp_epoch` — numeric comparison/debug value

Downstream filters should prefer `timestamp_epoch`, then `timestamp_iso`, and only fall back to `time` parsing if older payloads lack raw fields.

## Boundary rule

If the day boundary is 4:00 JST:

- a message at `02:00 JST` belongs to the previous operational day
- a message at `05:00 JST` belongs to the current operational day

A direct verification case is worth keeping around mentally:

- `within_day_window(02:00) == False`
- `within_day_window(05:00) == True`

## Where stale-looking results usually come from

When old messages seem to persist, check in this order:

1. Was the snapshot rebuilt after the boundary crossed?
2. Does the snapshot header show the expected `generated_operational_day`?
3. Is the consumer reading a fresh managed snapshot or an older derived file?
4. Is filtering using raw timestamps, or reparsing lossy display strings?

## Debug signals to expose

Helpful fields in debug output:

- `generated_at`
- `generated_operational_day`
- `day_start_hour`
- `recent.oldest_message_at`
- `recent.newest_message_at`
- per-message `timestamp_iso` / `timestamp_epoch`

These make it easy to separate stale-snapshot problems from actual boundary-filter bugs.
