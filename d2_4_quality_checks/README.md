# D2.4 Pluggable data-quality checks

- `Check.run(records, now=None) -> CheckResult(name, passed, failed_count, sample_failures[≤5], severity)`.
- Row-level checks use a template method: the base `run()` loops and counts; subclasses implement only
  `is_bad(value)` — `NotNull`, `Unique` (state cleared per run), `InRange` (numeric strings become `Decimal`),
  `MatchesPattern` (`fullmatch`).
- `Freshness` is dataset-level and overrides `run()`: the **newest** timestamp must be within `max_age` of
  `now`. No valid timestamp at all = fail. Unparsable values are ignored here (other checks catch them).
- `QualitySuite` runs every check the same way (no isinstance), with an injectable clock; a check that
  crashes becomes a failed result instead of killing the run. `passed` is False only when an
  `error`-severity check fails; `warning` checks just report. `write_report()` writes JSON with the UTC `run_at`.

Known limit: the suite materialises records in a list because each check needs its own pass.
