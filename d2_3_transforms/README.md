# D2.3 Chainable transforms

```python
pipeline = CsvSource("orders.csv") | Cast(schema) | Deduplicate("order_id") | Filter(is_paid)
stats = pipeline.into(JsonLinesSink("orders.jsonl"))
```

- `Transform.apply(record) -> dict | None` (None = drop). Implementations: `Filter`, `Rename`, `Cast`,
  `Deduplicate` (stateful, cleared by `reset()` at the start of each run).
- Operators: `Source | Transform` → `Pipeline` (via `Transform.__ror__`, since sources don't know about
  transforms); `Pipeline | Transform` → new `Pipeline`; `Transform | Transform` → `Chain` (a composite that
  is itself a Transform).
- `Pipeline` *composes* a source, a list of transforms and a sink — it does not inherit from them.
- A transform that raises on one record: the record goes to `stats.rejects` with step name and
  `"ExceptionClass: message"`; the run continues.
- `RunStats` has `read / written / dropped / rejects` and per-step `rows_in / rows_out / rejected` (used by the capstone report).
- `process(records, reset=True)` runs the transforms over any iterable without a sink (minietl uses it per file).

Known limit: transforms never mutate input, so each step copies the dict (a little extra allocation).
