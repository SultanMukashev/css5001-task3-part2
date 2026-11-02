# minietl — capstone

A command-line tool that runs JSON-configured pipelines: dated source files → transforms → partitioned
output, with quarantine, retries, a watermark/ledger, quality checks and a JSON run report.

## Run

From `part2/` (config paths are relative to it):

```bash
python -m capstone_minietl.make_sample_data          # (re)creates capstone_minietl/data/
python -m capstone_minietl run capstone_minietl/configs/orders.json -v
python -m capstone_minietl run capstone_minietl/configs/orders.json     # 2nd run: nothing_to_do
mv capstone_minietl/data/late/orders_2026-10-14.csv capstone_minietl/data/incoming/orders/
python -m capstone_minietl run capstone_minietl/configs/orders.json     # picks up the late file only
python -m capstone_minietl run capstone_minietl/configs/clicks.json
python -m pytest -q capstone_minietl
```

Exit codes: `0` success / nothing to do, `1` run failed (error-level check or a file that could not be
fetched), `2` config error (message names the exact config path).

Outputs (under `capstone_minietl/out/`):
- `orders/year=YYYY/month=MM/day=DD/<source file stem>.jsonl` – partitioned by **UTC** date.
- `quarantine/orders/<source file stem>.jsonl` – each bad record with `reason` (`step: error`).
- `state/orders.json` – watermark + sha256 of every loaded file.
- `reports/orders/run_<UTC start>.json` – status, start/end (UTC), duration, files (with a `late` flag),
  rows in/out/rejected per step, check results.

## Config

```json
{
  "source": {"type": "dated_files", "path": "...", "pattern": "orders_(?P<date>\\d{4}-\\d{2}-\\d{2})\\.csv", "format": "csv"},
  "transforms": [{"type": "require", "columns": [...]}, {"type": "cast", "schema": "orders"},
                 {"type": "normalise_ts", "column": "order_date", "source_tz": "Asia/Almaty"},
                 {"type": "dedupe", "key": "order_id"}],
  "checks": [{"type": "unique", "column": "order_id"}, {"type": "freshness", "column": "order_date", "max_age_hours": 72, "severity": "warning"}],
  "sink": {"type": "partitioned_jsonl", "path": "...", "ts_column": "order_date"},
  "retry": {"max_attempts": 3, "base": 0.5},
  "state": "...", "quarantine": "...", "reports": "..."
}
```

Plugins available: everything from D2.6 plus `dated_files` (source), `require`, `normalise_ts`
(transforms) and `partitioned_jsonl` (sink).

## How each requirement is met

| Requirement | Where |
|---|---|
| Pipelines from JSON via the registry | `runner.run` → D2.6 `build()`; new plugins in `plugins.py` register themselves |
| Incremental + idempotent | state holds the watermark **and** a sha256 per file; a file is loaded only if new or changed. Output files are per source file and swapped in atomically, so reloading replaces, never duplicates |
| Late-arriving file | the hash ledger (not only the date) decides, so a file older than the watermark still loads; report marks it `"late": true` |
| Quarantine, never stop | source parse errors, transform errors and un-partitionable rows all go to the quarantine file with a reason |
| Corrupt file | non-UTF-8 → cp1251 with `errors="replace"`, broken rows quarantined; a `csv.Error` quarantines the rest of that file only |
| Retry transient failures | `fetch()` (the I/O step) wrapped with the D1.5 `retry`; an exhausted file is reported, the run continues, status = failed, and the file is retried next run |
| Partitioned by UTC date | `normalise_ts` (D1.2) + `PartitionedJsonlSink` using `partition_path` |
| Quality suite after each load | D2.4 suite on all rows loaded in this run; error-level failure → `status: failed`, exit 1 |
| Run report | `reports/.../run_*.json` |
| Contract tests | `test_contracts.py`: every source, sink, transform and check |

## Known limits
- Dedupe works across files *within one run*, not against rows loaded by earlier runs.
- Quality checks run on rows held in memory for the current run (fine for daily files).
- If a changed file's rows move to different partitions, the old files of that batch are removed by
  globbing the output tree — cheap for a week of data, slow for years of partitions.
- Paths in configs are relative to the working directory.
- No parallelism: files are processed one after another, in date order.
