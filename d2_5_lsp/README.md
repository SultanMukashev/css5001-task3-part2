# D2.5 Find and fix the LSP violations

Sink contract: `write(records)` accepts **any** iterable (empty, generator, list) and returns the **number
written** (an int); `flush()`/`close()` work on every sink.

| Provided class | What it does | LSP rule broken |
|---|---|---|
| `BatchSink` | raises `ValueError` for < 100 records | **Strengthened precondition** – the base accepts any iterable, including empty; the subclass demands ≥ 100, so callers valid for `Sink` now fail. |
| `DryRunSink` | returns `None` | **Weakened postcondition** – the base promises an int count; code like `total += sink.write(...)` breaks. |
| `WarehouseSink` | `flush()` raises `NotImplementedError` | **New exception** – the base `flush()` never raises; every `with sink:` block now crashes on exit (`__exit__` calls `flush`). Also a refused bequest: it inherits a promise it won't keep. |

The originals live in `broken.py`. `contract_violations(factory)` runs the contract (empty list, one-shot
generator of 3, list of 150, inside a `with`) and labels each failure with the rule. The tests are
parametrised over the fixed sinks **and** the D2.2 sinks; separate tests prove each broken class is caught
with the right label.

Redesign (`solution.py`)
- `BatchSink` buffers; every full batch of `batch_size` is shipped, the remainder ships on `flush()`, which
  the base `__exit__` calls on close. Trade-off: `write()` returns "accepted", not "durably stored" — rows
  sitting in the buffer are lost if the process dies before `close()`. Callers who need durability call
  `flush()` explicitly; batching efficiency is kept.
- `DryRunSink` still writes nothing but returns the count it *would* have written (and logs each record).
  Trade-off: the count means "would write", which is exactly what a dry run should report.
- `WarehouseSink` stages rows on `write()` and commits them in `flush()`. Trade-off: data appears in the
  table only at flush/close (transaction-like), which is also what you want for a warehouse load.
