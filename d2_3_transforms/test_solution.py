import json
from decimal import Decimal
from pathlib import Path

from d2_2_sources_sinks.solution import CsvSource, InMemorySink, InMemorySource, JsonLinesSink
from d2_3_transforms.solution import Cast, Chain, Deduplicate, Filter, Pipeline, Rename

SAMPLE = Path(__file__).parents[1] / "data" / "orders.csv"
SCHEMA = {"order_id": int, "amount": Decimal}


def is_paid(r):
    return r["amount"] > 0


def test_readme_example(tmp_path):
    pipeline = CsvSource(SAMPLE) | Cast(SCHEMA) | Deduplicate("order_id") | Filter(is_paid)
    assert isinstance(pipeline, Pipeline)
    stats = pipeline.into(JsonLinesSink(tmp_path / "orders.jsonl"))
    assert (stats.read, stats.written, stats.dropped, len(stats.rejects)) == (5, 3, 1, 1)
    assert stats.rejects[0]["step"] == "Cast" and "abc" in stats.rejects[0]["error"]
    ids = [json.loads(l)["order_id"] for l in (tmp_path / "orders.jsonl").open(encoding="utf-8")]
    assert ids == [1001, 1002, 1004]
    assert [(s.name, s.rows_in, s.rows_out, s.rejected) for s in stats.steps] == [
        ("Cast", 5, 4, 1), ("Deduplicate", 4, 3, 0), ("Filter", 3, 3, 0)]


def test_rename_filter_and_no_mutation():
    data = [{"a": 1}, {"a": 2}]
    sink = InMemorySink()
    stats = (InMemorySource(data) | Rename({"a": "b"}) | Filter(lambda r: r["b"] > 1)).into(sink)
    assert sink.records == [{"b": 2}] and stats.dropped == 1


def test_transform_or_transform_builds_chain():
    chain = Rename({"x": "y"}) | Cast({"y": int}) | Filter(lambda r: r["y"] > 0)
    assert isinstance(chain, Chain) and len(chain.steps) == 3
    assert chain.apply({"x": "5"}) == {"y": 5}
    assert chain.apply({"x": "-1"}) is None


def test_errors_go_to_rejects():
    sink = InMemorySink()
    stats = (InMemorySource([{"id": 1}, {"nope": 1}, {"id": "x"}]) | Deduplicate("id")
             | Cast({"id": int})).into(sink)
    assert sink.records == [{"id": 1}]
    assert [r["step"] for r in stats.rejects] == ["Deduplicate", "Cast"]


def test_dedupe_state_reset_between_runs():
    p = InMemorySource([{"id": 1}, {"id": 1}]) | Deduplicate("id")
    assert p.into(InMemorySink()).written == 1
    assert p.into(InMemorySink()).written == 1


def test_empty_input():
    stats = (InMemorySource([]) | Cast(SCHEMA)).into(InMemorySink())
    assert (stats.read, stats.written) == (0, 0)
