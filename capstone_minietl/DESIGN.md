# minietl — design note

## Inheritance (each is an "is-a" that keeps the parent's promises)

- `Connector → Source / Sink`: one lifecycle (`open/close`, `with`). Sources promise `read()` streams dicts;
  sinks promise `write(any iterable) -> int` and a safe `flush()`.
- `Source → CsvSource, JsonLinesSource, InMemorySource, DatedFileSource`; `Sink → CsvSink, JsonLinesSink,
  InMemorySink, BatchSink, DryRunSink, WarehouseSink, PartitionedJsonlSink`. `_FileConnector` is a small
  mixin that holds the file-handle code shared by file connectors.
- `Transform → Filter, Rename, Cast, Deduplicate, Chain, Require, NormaliseTs`: all promise
  `apply(dict) -> dict | None` without mutating the input.
- `Check → NotNull, Unique, InRange, MatchesPattern, Freshness`: row checks fill in the `is_bad()` step of
  the base `run()` (template method); `Freshness` overrides `run()` because it judges the dataset.
- `Registered` mixin + `__init_subclass__`: plugin classes (e.g. `d2_6.Cast(d2_3.Cast, Registered, kind=..., name=...)`)
  inherit behaviour from the real class and only add a registry entry. That keeps the registry out of the
  domain classes.

## Composition (has-a, preferred where behaviour is combined, not specialised)

- `Pipeline` **has** a source and a list of transforms; the sink is passed to `into()`. Pipelines are built
  with `|`, never by subclassing.
- `Chain` **has** transforms and is itself a `Transform` (composite), so `a | b` can be used anywhere one transform can.
- `QualitySuite` **has** checks; `BuiltPipeline` **has** a pipeline, a suite and a sink.
- The runner **wraps** `source.fetch` with the retry decorator instead of making a "RetryingSource" subclass;
  any source with `list_files/fetch/parse` becomes incremental and retried.
- `BatchSink` takes a `ship` callable instead of being subclassed per destination.

## How the design satisfies LSP

- **Preconditions not strengthened:** every sink accepts empty input and one-shot generators; transforms
  accept any dict (bad ones raise ordinary `Exception`s that the pipeline turns into rejects).
- **Postconditions not weakened:** `write()` always returns an int count; `run()` always returns a
  well-formed `CheckResult` (passed ⇔ failed_count == 0, ≤ 5 samples); transforms return dict or None.
- **No new exceptions:** `flush()`/`close()` never raise on healthy sinks; a crashing check becomes a
  failed result, not an exception out of the suite.
- **Proved by tests, not by promise:** `test_contracts.py` runs the same contract over every subclass
  (the D2.5 `contract_violations` checker for sinks). D2.5's three broken sinks fail it, each labelled
  with the rule it breaks; their redesigns pass.
- `PartitionedJsonlSink` overrides `__exit__` only to *discard* temp files on an exception; on the normal
  path it calls the parent's `__exit__`, so `flush + close` still happen as promised.
