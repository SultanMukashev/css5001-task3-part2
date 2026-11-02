# D1.1 Resilient CSV ingestion

Run: `python -m d1_1_resilient_ingest.solution [orders.csv]` from `part2/`. Writes `clean.csv` and
`rejects.csv` next to the input (or into `out_dir=`) and prints the run summary.

Design
- `ValidationError` → `MissingField`, `InvalidAmount`, `DuplicateKey`, `MalformedRow`. Each row is validated
  in its own `try`; a rejected row gets `reason = "<ExceptionClass>: <message>"`.
- The `reason` group in the summary is the exception class name.
- Amounts are `Decimal`; `NaN`/`Infinity` and negatives are rejected (zero is allowed, the task says "negative").
- Duplicate key = an `order_id` already *accepted*; the first copy wins.
- Encoding: the file is first decoded once end-to-end as UTF-8 (streaming, nothing kept in memory). Only if
  that raises `UnicodeDecodeError` do we switch to `fallback_encoding` (default `cp1251`). Checking up front
  means we never write half a run with one encoding and then restart. `utf-8-sig` also strips an Excel BOM.
- Rows with too many cells → `MalformedRow`; too few → `MissingField`.

Known limits
- Email format and date validity are left to D1.2/D1.3 (as the task says), so row 1002 is accepted here.
- Fallback is tried once; a file that is neither UTF-8 nor the fallback still decodes as garbage in cp1251
  (cp1251 maps almost every byte), and rows then fail validation instead of crashing.
