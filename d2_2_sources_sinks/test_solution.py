import csv
import json
import tracemalloc

import pytest

from d2_2_sources_sinks.solution import (
    CsvSink, CsvSource, InMemorySink, InMemorySource, JsonLinesSink, JsonLinesSource,
)

DATA = [{"id": "1", "name": "Aru"}, {"id": "2", "name": "Дана"}]


def make_source(kind, tmp_path):
    if kind == "csv":
        p = tmp_path / "in.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, ["id", "name"]); w.writeheader(); w.writerows(DATA)
        return CsvSource(p)
    if kind == "jsonl":
        p = tmp_path / "in.jsonl"
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in DATA), encoding="utf-8")
        return JsonLinesSource(p)
    return InMemorySource(DATA)


def make_sink(kind, tmp_path):
    return {"csv": lambda: CsvSink(tmp_path / "out" / "o.csv"),
            "jsonl": lambda: JsonLinesSink(tmp_path / "out" / "o.jsonl"),
            "memory": InMemorySink}[kind]()


def read_back(sink):
    if isinstance(sink, InMemorySink):
        return sink.records
    with sink.path.open(encoding="utf-8", newline="") as f:
        if sink.path.suffix == ".csv":
            return list(csv.DictReader(f))
        return [json.loads(line) for line in f]


@pytest.mark.parametrize("src_kind", ["csv", "jsonl", "memory"])
@pytest.mark.parametrize("sink_kind", ["csv", "jsonl", "memory"])
def test_matrix(src_kind, sink_kind, tmp_path):
    src, sink = make_source(src_kind, tmp_path), make_sink(sink_kind, tmp_path)
    with src, sink:
        assert sink.write(src.read()) == 2
    assert read_back(sink) == DATA


@pytest.mark.parametrize("sink_kind", ["csv", "jsonl", "memory"])
def test_empty_write(sink_kind, tmp_path):
    with make_sink(sink_kind, tmp_path) as sink:
        assert sink.write([]) == 0
        assert sink.write(iter(())) == 0


def test_read_outside_with_block_is_clear_error(tmp_path):
    with pytest.raises(RuntimeError, match="with"):
        next(make_source("csv", tmp_path).read())


def test_jsonl_skips_bad_lines(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n{broken\n\n[1]\n{"a": 2}\n', encoding="utf-8")
    with JsonLinesSource(p) as src:
        assert [r["a"] for r in src.read()] == [1, 2]
    assert [n for n, _ in src.bad_lines] == [2, 4]


def test_file_closed_after_exception(tmp_path):
    sink = make_sink("jsonl", tmp_path)
    with pytest.raises(ZeroDivisionError):
        with sink:
            1 / 0
    assert sink._fh is None


def test_source_streams(tmp_path):
    p = tmp_path / "big.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for i in range(200_000):
            f.write(json.dumps({"i": i, "pad": "x" * 50}) + "\n")
    tracemalloc.start()
    with JsonLinesSource(p) as src:
        count = sum(1 for _ in src.read())
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert count == 200_000
    assert peak < 2_000_000  # file is ~14 MB; streaming keeps memory tiny
