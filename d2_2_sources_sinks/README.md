# D2.2 Source and sink hierarchy

```
Connector (ABC)  open() / close() no-ops, __enter__/__exit__
├── Source       read() -> Iterator[dict]        (abstract)
│   ├── CsvSource, JsonLinesSource   (via _FileConnector: opens/closes the file)
│   └── InMemorySource
└── Sink         write(records) -> int (abstract), flush(); __exit__ = flush + close
    ├── CsvSink, JsonLinesSink       (via _FileConnector, mode "w")
    └── InMemorySink
```

- The `with` logic lives only in the base classes; connectors only override `open()`/`close()`.
- Sources stream: `csv.DictReader` and line iteration over an open file. A test reads a ~14 MB file and
  checks peak memory stays under 2 MB with `tracemalloc`.
- `read()`/`write()` outside a `with` block raise a clear `RuntimeError`.
- `JsonLinesSource` skips bad lines and records them in `bad_lines` instead of failing.
- File sinks open with `"w"` → re-running overwrites (idempotent).
- Test: 3 × 3 matrix pairing every source with every sink.

Known limit: `CsvSink` takes its columns from the first record; keys that first appear later are dropped.
