# CSS5001 Task 3, Part 2: Data Engineering in plain Python

A small ETL toolkit and the `minietl` command-line tool built on it. It is written with the
**Python standard library only** (plus `pytest` for tests).

The tasks build on each other. D1 is the ingestion layer: validating messy files, normalising dates
and text, loading incrementally and retrying unreliable sources. D2 turns that into an extensible
framework of typed records, interchangeable sources and sinks, chainable transforms and pluggable
quality checks. The capstone combines both into one config-driven pipeline runner.

- **207 tests**, all deterministic: injected clocks and sleeps, `tmp_path`, no network.
- Every task folder has its own `README.md` covering how to run it, design decisions and known limits.

---

## Quick start

Requires **Python 3.11+**.

```bash
git clone https://github.com/SultanMukashev/css5001-task3-part2.git
cd css5001-task3-part2
python -m pip install pytest
python -m pytest -q                      # 207 passed
```

Run any task as a module **from the repo root**. The tasks import each other, so
`python solution.py` from inside a folder will not work.

```bash
python -m d1_1_resilient_ingest.solution data/orders.csv
python -m d1_2_dates.solution
python -m capstone_minietl run capstone_minietl/configs/orders.json -v
```

---

## Repository layout

```
.
├── data/orders.csv              # sample with one deliberate problem per row (D1.1–D1.3, D2.3, D2.6)
├── d1_1_resilient_ingest/       # each task folder: solution.py, test_solution.py, README.md
├── d1_2_dates/
├── d1_3_text_cleaning/
├── d1_4_incremental_loader/
├── d1_5_retry/
├── d1_6_sessions/
├── d2_1_order_model/
├── d2_2_sources_sinks/
├── d2_3_transforms/
├── d2_4_quality_checks/
├── d2_5_lsp/                    # + broken.py: the three provided LSP-violating sinks
├── d2_6_registry/
└── capstone_minietl/            # the minietl CLI: plugins, runner, configs, sample data, DESIGN.md
```

---

## Tasks

### D1: Exceptions, dates, regex and files

| Task | Level | What it does | Key ideas | Tests |
|---|---|---|---|---|
| [D1.1 Resilient ingest](d1_1_resilient_ingest/) | Core | Splits a CSV into `clean.csv` and `rejects.csv` (with a `reason` column) and prints a run summary | `ValidationError` hierarchy caught per row, `Decimal` amounts, UTF-8 then cp1251 fallback | 11 |
| [D1.2 Dates](d1_2_dates/) | Core | Converts any sample date format to UTC ISO 8601 and builds `year=/month=/day=` partitions | `zoneinfo`, explicit `dayfirst`, DST gap and overlap, year rollover | 14 |
| [D1.3 Text cleaning](d1_3_text_cleaning/) | Core | Normalises phones to `+7-701-123-4567`, validates emails, masks PII, strips HTML | `re.sub` with replacement functions, `fullmatch` | 12 |
| [D1.4 Incremental loader](d1_4_incremental_loader/) | Advanced | Processes only daily files newer than a watermark; re-runs do nothing | atomic `os.replace` writes, temp-then-swap output, per-line error logging | 6 |
| [D1.5 Retry](d1_5_retry/) | Advanced | `@retry` decorator with exponential backoff and jitter | retries only transient errors, `RetryExhausted` chained from the last error, injectable `sleep` | 4 |
| [D1.6 Sessions](d1_6_sessions/) | Challenge | Groups click events into sessions split by 30 minutes of inactivity | out-of-order input, mixed time zones, sessions crossing midnight | 6 |

### D2: Classes, inheritance, polymorphism and LSP

| Task | Level | What it does | Key ideas | Tests |
|---|---|---|---|---|
| [D2.1 Order model](d2_1_order_model/) | Core | Frozen `Order` dataclass with validation and `from_row` / `to_row` | `__post_init__`, classmethods, round-trip guarantee | 20 |
| [D2.2 Sources and sinks](d2_2_sources_sinks/) | Core | CSV, JSON Lines and in-memory sources and sinks that all work in `with` blocks | ABCs, context managers, streaming (memory-tested on a 14 MB file), 3 × 3 pairing matrix | 16 |
| [D2.3 Transforms](d2_3_transforms/) | Core | `Filter`, `Rename`, `Cast`, `Deduplicate` composed with `\|` into pipelines | operator overloading (`__or__`, `__ror__`), composite `Chain`, per-record rejects | 6 |
| [D2.4 Quality checks](d2_4_quality_checks/) | Advanced | `NotNull`, `Unique`, `InRange`, `MatchesPattern`, `Freshness` and a `QualitySuite` with a JSON report | template method, error vs warning severity | 12 |
| [D2.5 LSP](d2_5_lsp/) | Advanced | Contract test suite for every sink; fixes three provided sinks that break it | strengthened precondition, weakened postcondition, new exception | 11 |
| [D2.6 Registry](d2_6_registry/) | Challenge | Builds a whole pipeline from a JSON config with no if-chains | `__init_subclass__` registry, `inspect.signature`, errors naming the exact config path | 12 |

### Capstone: `minietl`

| Task | What it does | Tests |
|---|---|---|
| [minietl](capstone_minietl/) | CLI that runs config-driven pipelines from dated source files through transforms and quality checks to UTC-partitioned output, with quarantine, retries, an incremental and idempotent state ledger, and a JSON run report | 77 (incl. contract tests for every source, sink, transform and check) |

---

## How the pieces fit together

```
                D1 (ingestion building blocks)
  D1.2 parse_ts / partition_path ─────┬──────────────┬──────────────┐
  D1.4 atomic_write_json ──────┐      │              │              │
  D1.5 retry ──────────────┐   │      ▼              ▼              ▼
                           │   │   D2.1 Order    D1.6 sessions  D2.4 Freshness
                D2 (framework)
  D2.2 Source / Sink ──► D2.3 Transform + Pipeline ──► D2.6 registry + build(config)
            │                                                  ▲
            └── D2.5 contract_violations() ── D2.4 QualitySuite ┘
                                   │
                                   ▼
                     capstone_minietl (uses all of the above)
```

A pipeline reads naturally:

```python
from decimal import Decimal
from d2_2_sources_sinks.solution import CsvSource, JsonLinesSink
from d2_3_transforms.solution import Cast, Deduplicate, Filter

pipeline = (CsvSource("data/orders.csv")
            | Cast({"order_id": int, "amount": Decimal})
            | Deduplicate("order_id")
            | Filter(lambda r: r["amount"] > 0))
stats = pipeline.into(JsonLinesSink("orders.jsonl"))
print(stats.read, stats.written, stats.rejects)   # a bad record is rejected, never crashes the run
```

The same pipeline can be built from JSON through the D2.6 registry:

```json
{
  "source": {"type": "csv", "path": "data/orders.csv"},
  "transforms": [{"type": "cast", "schema": "orders"}, {"type": "dedupe", "key": "order_id"}],
  "checks": [{"type": "not_null", "column": "customer_email"}],
  "sink": {"type": "jsonl", "path": "out/orders.jsonl"}
}
```

A mistake in the config fails fast with the exact path, for example
`transforms[1].key: missing required parameter`.

---

## minietl demo

```bash
python -m capstone_minietl.make_sample_data                               # a week of messy orders + clicks
python -m capstone_minietl run capstone_minietl/configs/orders.json       # loads 6 files
python -m capstone_minietl run capstone_minietl/configs/orders.json       # status=nothing_to_do (idempotent)
mv capstone_minietl/data/late/orders_2026-10-14.csv capstone_minietl/data/incoming/orders/
python -m capstone_minietl run capstone_minietl/configs/orders.json       # loads only the late file
```

Output of the first run:

```
status=success files=6 duration=0.019s report=capstone_minietl/out/reports/orders/run_...json
  source         in=245   out=238   rejected=7
  Require        in=238   out=233   rejected=5
  Cast           in=233   out=228   rejected=5
  NormaliseTs    in=228   out=223   rejected=5
  Deduplicate    in=223   out=218   rejected=0
  sink           in=218   out=218   rejected=0
  [ok  ] NotNull(customer_email) failed=0
  [ok  ] Unique(order_id) failed=0
  [warn] InRange(amount) failed=5
  [warn] MatchesPattern(currency) failed=5
  [warn] Freshness(order_date) failed=1
```

Everything it writes goes under `capstone_minietl/out/`:

| Path | Contents |
|---|---|
| `orders/year=YYYY/month=MM/day=DD/*.jsonl` | loaded rows, partitioned by **UTC** date |
| `quarantine/orders/*.jsonl` | every rejected record with the step and reason |
| `state/orders.json` | watermark plus a sha256 of every loaded file |
| `reports/orders/run_*.json` | start and end time (UTC), duration, rows in/out/rejected per step, check results |

Exit codes: `0` success or nothing to do, `1` run failed (an error-level check, or a file that could not be fetched), `2` config error.
The design note [capstone_minietl/DESIGN.md](capstone_minietl/DESIGN.md) explains each inheritance relation, each
use of composition, and how the design satisfies LSP.

---

## Principles followed throughout

- **One bad record never stops a run.** It is counted, given a reason and quarantined or reported.
- **Specific, chained exceptions:** `InvalidAmount`, `InvalidDate`, `RetryExhausted ... from ConnectionError`, `ConfigError`.
- **Timestamps are stored in UTC ISO 8601.** Naive values are read in an explicit source time zone; ambiguous `01/10/2026` needs an explicit `dayfirst`.
- **Text files are opened with `encoding="utf-8"`** (with an explicit fallback only where the task asks for one).
- **Re-runs are safe.** Outputs are written to a temp file and atomically swapped in, and state is updated only after a file is fully committed.
- **Substitutable subclasses.** Every source, sink, transform and check passes the same contract tests.
- **Deterministic tests.** Time, sleep and randomness are injected; file tests use `tmp_path`.

---

## Known limits

The main ones are listed here; each task's README has the full list.

- `CsvSink` takes its columns from the first record; keys that first appear later are dropped.
- minietl deduplicates across files within one run, not against rows loaded by earlier runs.
- Quality checks hold the current run's rows in memory (fine for daily files).
- Regex HTML stripping (D1.3) is only for trusted, simple markup, not a general HTML parser. The README explains why.
