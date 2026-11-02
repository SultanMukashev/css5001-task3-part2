# D1.2 Date normalisation and partition keys

API: `normalise_ts(value, source_tz, dayfirst=True) -> "YYYY-MM-DDTHH:MM:SS+00:00"`,
`parse_ts(...) -> aware UTC datetime` (reused by D1.6, D2.1, D2.4, minietl),
`partition_path(ts) -> "year=2026/month=10/day=01"`, `write_partitioned(records, out_dir, ts_field, source_tz)`.

Formats: anything `datetime.fromisoformat` accepts (3.11+: `2026-10-01`, `...T14:30:00+02:00`, `...Z`), plus
`DD/MM/YYYY`, `MM/DD/YYYY` (by `dayfirst`) and `DD.MM.YYYY`, each with optional ` HH:MM[:SS]`.

Why ambiguity needs an explicit decision: `01/10/2026` is 1 October in Kazakhstan/Europe and 10 January
in the US. Both are valid dates, so no parser can detect the mistake; guessing silently shifts data by
months and puts it in the wrong partition. The caller knows the source system, so they pass `dayfirst`.
Dotted dates are always day-first (no common format puts the month first there).

Time zones
- Naive values are local time in `source_tz`; values with an offset keep it, and `source_tz` is ignored.
- DST overlap (e.g. 02:30 on 25 Oct 2026 in Berlin happens twice): we take the **earlier** occurrence (`fold=0`).
- DST gap (02:30 on 29 Mar 2026 in Berlin does not exist): `InvalidDate`. Shifting it silently would invent data.
- Impossible dates (`2026-13-01`) raise `InvalidDate` with the original value in the message.

`write_partitioned` overwrites `records.jsonl` in each partition, so re-running a batch is safe.

Known limits: an unknown `source_tz` raises `ZoneInfoNotFoundError` (a config bug, not a bad record).
`write_partitioned` groups a batch in memory.
