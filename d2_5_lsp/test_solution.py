import pytest

from d2_2_sources_sinks.solution import CsvSink, InMemorySink, JsonLinesSink
from d2_5_lsp import broken
from d2_5_lsp.solution import BatchSink, DryRunSink, WarehouseSink, contract_violations


def all_sinks(tmp_path):
    return {
        "BatchSink": BatchSink,
        "DryRunSink": DryRunSink,
        "WarehouseSink": WarehouseSink,
        "InMemorySink": InMemorySink,
        "CsvSink": lambda: CsvSink(tmp_path / "o.csv"),
        "JsonLinesSink": lambda: JsonLinesSink(tmp_path / "o.jsonl"),
    }


@pytest.mark.parametrize("name", ["BatchSink", "DryRunSink", "WarehouseSink",
                                  "InMemorySink", "CsvSink", "JsonLinesSink"])
def test_every_sink_honours_contract(name, tmp_path):
    assert contract_violations(all_sinks(tmp_path)[name]) == []


@pytest.mark.parametrize("cls,rule", [
    (broken.BatchSink, "strengthened precondition"),
    (broken.DryRunSink, "weakened postcondition"),
    (broken.WarehouseSink, "new exception"),
])
def test_broken_sinks_are_caught(cls, rule):
    problems = contract_violations(cls)
    assert problems and all(rule in p for p in problems)


def test_batch_sink_flushes_remainder_on_close():
    sink = BatchSink(batch_size=100)
    with sink:
        assert sink.write({"i": i} for i in range(250)) == 250
        assert [len(b) for b in sink.shipped] == [100, 100]
    assert [len(b) for b in sink.shipped] == [100, 100, 50]


def test_warehouse_commits_on_exit():
    sink = WarehouseSink()
    with sink:
        sink.write([{"a": 1}])
        assert sink.table == []
    assert sink.table == [{"a": 1}]
