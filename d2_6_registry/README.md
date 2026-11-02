# D2.6 Config-driven pipelines with a plugin registry

```python
from d2_6_registry.solution import build, load_config
stats, quality = build(load_config("pipeline.json")).run()
```

- `Registered.__init_subclass__(kind=..., name=...)` records every plugin class in
  `Registered.registry[kind][name]`; registering the same name twice raises `TypeError`.
- Plugins are thin subclasses of the D2.2–D2.4 classes that only add a short name (`csv`, `jsonl`, `cast`,
  `dedupe`, `rename`, `filter`, `not_null`, `unique`, `in_range`, `matches_pattern`, `freshness`). Earlier
  task code is left unchanged. Config-friendly wrappers: `cast` takes a schema *name* (`SCHEMAS`),
  `filter` takes `column`/`equals`, `freshness` takes `max_age_hours`.
- `build()` has no if-chains: it looks up the class by `type`, checks parameters against
  `inspect.signature(cls)` and calls it. Errors are `ConfigError` starting with the exact path:
  `transforms[1].key: missing required parameter`, `transforms[0].type: unknown transform type 'explode'`,
  `transforms[0].schema: unknown schema 'nope'` (plugins raise `ParamError(param, msg)` to blame one parameter).
- `BuiltPipeline.run()` loads source → transforms → sink and runs the quality suite on what was loaded.

Known limit: a `filter` from config can only test equality; arbitrary predicates need code.
