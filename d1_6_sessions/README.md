# D1.6 Clickstream sessionisation

Run: `python -m d1_6_sessions.solution clicks.csv sessions.csv [source_tz]`.

- Timestamps go through the D1.2 parser → UTC; naive ones use `source_tz`.
- Events are grouped per user and sorted, so out-of-order and mixed-zone input is fine.
- A new session starts when the gap is **strictly greater** than 30 minutes (exactly 30 min stays in the session).
- Sessions are compared on UTC instants, so crossing midnight (or a DST change) needs no special case.
- Bad events (missing user, bad timestamp) are returned as `rejected`, never crash the run.
- Output row: `user_id, start, end, duration_seconds, page_count`.

Known limit: all events are held in memory, grouped by user (fine for a daily file; for huge inputs sort externally by user, time first).
