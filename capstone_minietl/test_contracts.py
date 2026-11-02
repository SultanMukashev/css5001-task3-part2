"""Contract tests: every source, sink, transform and check honours its base-class promise."""
import csv
import json
from datetime import timedelta
from numbers import Integral

import pytest

from capstone_minietl.plugins import DatedFileSource, NormaliseTs, PartitionedJsonlSink, Require
from d2_2_sources_sinks.solution import (
    CsvSink, CsvSource, InMemorySink, InMemorySource, JsonLinesSink, JsonLinesSource,
)
from d2_3_transforms.solution import Cast, Chain, Deduplicate, Filter, Rename
from d2_4_quality_checks.solution import (
    CheckResult, Freshness, InRange, MatchesPattern, NotNull, Unique,
)
from d2_5_lsp.solution import BatchSink, DryRunSink, WarehouseSink, contract_violations

ROWS = [{"id": "1", "ts": "2026-10-01T10:00:00+00:00"}, {"id": "2", "ts": "2026-10-02T10:00:00+00:00"}]


# ---------- sources: read() in a with block yields dicts; empty input yields nothing ----------

def _sources(tmp, rows):
    csv_p, jl_p, d = tmp / "s.csv", tmp / "s.jsonl", tmp / "dated"
    d.mkdir(exist_ok=True)
    with open(csv_p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["id", "ts"]); w.writeheader(); w.writerows(rows)
    jl_p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (d / "x_2026-10-01.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {
        "CsvSource": CsvSource(csv_p),
        "JsonLinesSource": JsonLinesSource(jl_p),
        "InMemorySource": InMemorySource(rows),
        "DatedFileSource": DatedFileSource(str(d), r"x_(?P<date>[\d-]+)\.jsonl", "jsonl"),
    }


SOURCE_NAMES = ["CsvSource", "JsonLinesSource", "InMemorySource", "DatedFileSource"]


@pytest.mark.parametrize("name", SOURCE_NAMES)
@pytest.mark.parametrize("rows", [ROWS, []], ids=["rows", "empty"])
def test_source_contract(name, rows, tmp_path):
    with _sources(tmp_path, rows)[name] as src:
        out = list(src.read())
    assert all(isinstance(r, dict) for r in out)
    assert out == rows


# ---------- sinks: shared D2.5 contract (any iterable, int count, flush/close never raise) ----------

SINKS = {
    "CsvSink": lambda p: CsvSink(p / "o.csv"),
    "JsonLinesSink": lambda p: JsonLinesSink(p / "o.jsonl"),
    "InMemorySink": lambda p: InMemorySink(),
    "BatchSink": lambda p: BatchSink(),
    "DryRunSink": lambda p: DryRunSink(),
    "WarehouseSink": lambda p: WarehouseSink(),
    "PartitionedJsonlSink": lambda p: PartitionedJsonlSink(str(p / "parts"), "ts"),
}


@pytest.mark.parametrize("name", list(SINKS))
def test_sink_contract(name, tmp_path):
    def make():
        sink = SINKS[name](tmp_path)
        real_write = sink.write
        # give each record a timestamp so the partitioned sink can place it
        sink.write = lambda recs: real_write({**r, "ts": "2026-10-01T00:00:00+00:00"} for r in recs)
        return sink
    assert contract_violations(make) == []


# ---------- transforms: return dict or None, never mutate input, fail with Exception only ----------

TRANSFORMS = {
    "Filter": lambda: Filter(lambda r: r.get("id") == "1"),
    "Rename": lambda: Rename({"id": "key"}),
    "Cast": lambda: Cast({"id": int}),
    "Deduplicate": lambda: Deduplicate("id"),
    "Chain": lambda: Rename({"x": "y"}) | Cast({"id": int}),
    "Require": lambda: Require(["id"]),
    "NormaliseTs": lambda: NormaliseTs("ts", "Asia/Almaty"),
}


@pytest.mark.parametrize("name", list(TRANSFORMS))
@pytest.mark.parametrize("record", [ROWS[0], ROWS[1], {}, {"id": None, "ts": "garbage"}])
def test_transform_contract(name, record):
    t = TRANSFORMS[name]()
    t.reset()
    before = dict(record)
    try:
        out = t.apply(record)
    except Exception:
        out = "raised"  # allowed: the pipeline turns it into a reject
    assert out is None or out == "raised" or isinstance(out, dict)
    assert record == before, "transform mutated its input"
    if isinstance(out, dict):
        assert out is not record or isinstance(t, (Filter, Deduplicate, Require, Chain))


def test_chain_is_a_transform():
    assert isinstance(TRANSFORMS["Chain"](), Chain)


# ---------- checks: always a well-formed CheckResult; sample capped; clean data passes ----------

CHECKS = {
    "NotNull": lambda: NotNull("id"),
    "Unique": lambda: Unique("id"),
    "InRange": lambda: InRange("id", 0, 10),
    "MatchesPattern": lambda: MatchesPattern("id", r"\d+"),
    "Freshness": lambda: Freshness("ts", timedelta(days=100_000)),
}


@pytest.mark.parametrize("name", list(CHECKS))
@pytest.mark.parametrize("rows", [ROWS, [], [{"id": None, "ts": None}] * 20, [{"id": "1"}] * 20],
                         ids=["clean", "empty", "nulls", "dupes"])
def test_check_contract(name, rows):
    res = CHECKS[name]().run(rows)
    assert isinstance(res, CheckResult) and isinstance(res.name, str)
    assert isinstance(res.passed, bool) and isinstance(res.failed_count, Integral)
    assert res.failed_count >= 0 and len(res.sample_failures) <= 5
    assert res.passed == (res.failed_count == 0)
    if rows is ROWS:
        assert res.passed
