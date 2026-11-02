import json
import logging

import pytest

from d1_4_incremental_loader.solution import read_watermark, run


@pytest.fixture
def dirs(tmp_path):
    inc, out = tmp_path / "in", tmp_path / "out"
    inc.mkdir()
    (inc / "events_2026-10-17.jsonl").write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    (inc / "events_2026-10-16.jsonl").write_text('{"id": 0}\n', encoding="utf-8")
    (inc / "notes.txt").write_text("hello", encoding="utf-8")
    return inc, out, tmp_path / "state" / "watermark.json"


def test_first_run_processes_in_date_order(dirs, caplog):
    inc, out, state = dirs
    caplog.set_level(logging.INFO)
    res = run(inc, out, state)
    assert [r["file"] for r in res] == ["events_2026-10-16.jsonl", "events_2026-10-17.jsonl"]
    assert str(read_watermark(state)) == "2026-10-17"
    assert "ignoring notes.txt" in caplog.text


def test_rerun_is_idempotent(dirs):
    inc, out, state = dirs
    run(inc, out, state)
    before = (out / "events_2026-10-17.jsonl").read_text(encoding="utf-8")
    assert run(inc, out, state) == []
    assert (out / "events_2026-10-17.jsonl").read_text(encoding="utf-8") == before


def test_new_file_arrives(dirs):
    inc, out, state = dirs
    run(inc, out, state)
    (inc / "events_2026-10-18.jsonl").write_text('{"id": 9}\n', encoding="utf-8")
    assert [r["file"] for r in run(inc, out, state)] == ["events_2026-10-18.jsonl"]
    assert str(read_watermark(state)) == "2026-10-18"


def test_crash_mid_file_keeps_watermark(dirs):
    inc, out, state = dirs
    run(inc, out, state)
    (inc / "events_2026-10-18.jsonl").write_text('{"id": 1}\n{"id": "boom"}\n', encoding="utf-8")

    def explode(r):
        if r["id"] == "boom":
            raise RuntimeError("disk full")
        return r

    with pytest.raises(RuntimeError):
        run(inc, out, state, transform=explode)
    assert str(read_watermark(state)) == "2026-10-17"
    assert not (out / "events_2026-10-18.jsonl").exists()
    assert not list(out.glob("*.tmp"))
    assert len(run(inc, out, state)) == 1  # recovers on the next run


def test_bad_lines_logged_with_location(dirs, caplog):
    inc, out, state = dirs
    (inc / "events_2026-10-19.jsonl").write_bytes(b'{"id": 1}\n{oops\n\n[1,2]\n\xff\xfe\n{"id": 2}\n')
    res = run(inc, out, state)[-1]
    assert (res["written"], res["bad"]) == (2, 3)
    assert "events_2026-10-19.jsonl:2" in caplog.text
    lines = (out / "events_2026-10-19.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["id"] for l in lines] == [1, 2]


def test_impossible_date_in_name_and_empty_dir(tmp_path, caplog):
    (tmp_path / "events_2026-13-01.jsonl").write_text("{}", encoding="utf-8")
    assert run(tmp_path, tmp_path / "out", tmp_path / "wm.json") == []
    assert "impossible date" in caplog.text
    assert read_watermark(tmp_path / "wm.json") is None
