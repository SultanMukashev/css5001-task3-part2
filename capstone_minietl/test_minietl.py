import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from capstone_minietl import plugins
from capstone_minietl.__main__ import main
from capstone_minietl.make_sample_data import generate
from capstone_minietl.runner import run
from d2_6_registry.solution import ConfigError

HERE = Path(__file__).parent


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 19, 6, tzinfo=UTC)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def env(tmp_path):
    generate(tmp_path / "data")
    cfg = json.loads((HERE / "configs" / "orders.json").read_text(encoding="utf-8"))
    cfg["source"]["path"] = str(tmp_path / "data" / "incoming" / "orders")
    cfg["sink"]["path"] = str(tmp_path / "out")
    for key in ("state", "quarantine", "reports"):
        cfg[key] = str(tmp_path / key)
    return tmp_path, cfg


def go(cfg, **kw):
    return run(cfg, clock=Clock(), sleep=lambda s: None, **kw)


def test_first_run(env):
    tmp, cfg = env
    rep = go(cfg)
    assert rep["status"] == "success"
    assert [f["file"] for f in rep["files"]] == [f"orders_2026-10-{d}.csv" for d in (12, 13, 15, 16, 17, 18)]
    assert rep["watermark"] == "2026-10-18"
    assert rep["started_at"] == "2026-10-19T06:00:01+00:00" and rep["duration_seconds"] > 0
    steps = {s["step"]: s for s in rep["steps"]}
    assert steps["sink"]["rows_out"] > 200 and steps["Cast"]["rejected"] > 0
    assert rep["quality"]["passed"]  # only warnings fail on the sample
    assert Path(rep["report_path"]).exists()


def test_output_partitioned_by_utc_date(env):
    tmp, cfg = env
    go(cfg)
    for f in (tmp / "out").rglob("*.jsonl"):
        y, m, d = (part.split("=")[1] for part in f.parent.relative_to(tmp / "out").parts)
        for line in f.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["order_date"].startswith(f"{y}-{m}-{d}T")
            assert json.loads(line)["order_date"].endswith("+00:00")
    # 2026-10-12 00:xx in +05:00/+09:00 lands on 11 October UTC
    assert (tmp / "out" / "year=2026" / "month=10" / "day=11").exists()


def test_rerun_is_idempotent(env):
    tmp, cfg = env
    go(cfg)
    snapshot = {p: p.read_bytes() for p in (tmp / "out").rglob("*.jsonl")}
    rep = go(cfg)
    assert rep["status"] == "nothing_to_do" and rep["files"] == []
    assert {p: p.read_bytes() for p in (tmp / "out").rglob("*.jsonl")} == snapshot


def test_late_file_and_changed_file(env):
    tmp, cfg = env
    go(cfg)
    shutil.move(tmp / "data" / "late" / "orders_2026-10-14.csv", tmp / "data" / "incoming" / "orders")
    rep = go(cfg)
    assert rep["files"][0]["file"] == "orders_2026-10-14.csv" and rep["files"][0]["late"]
    assert rep["watermark"] == "2026-10-18"
    f = tmp / "data" / "incoming" / "orders" / "orders_2026-10-12.csv"
    f.write_text(f.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")  # now empty
    rep = go(cfg)
    assert [x["file"] for x in rep["files"]] == ["orders_2026-10-12.csv"]
    assert not list((tmp / "out").rglob("orders_2026-10-12.jsonl"))  # old output replaced


def test_quarantine_has_reasons(env):
    tmp, cfg = env
    go(cfg)
    rows = [json.loads(l) for l in (tmp / "quarantine" / "orders_2026-10-12.jsonl").open(encoding="utf-8")]
    reasons = " | ".join(r["reason"] for r in rows)
    for expected in ("missing customer_email", "not a number", "cannot parse date", "too few fields"):
        assert expected in reasons


def test_corrupt_file_does_not_stop_run(env):
    tmp, cfg = env
    rep = go(cfg)
    corrupt = next(f for f in rep["files"] if f["file"] == "orders_2026-10-15.csv")
    assert corrupt["rejected"] > 0 and corrupt["written"] > 0


def test_transient_fetch_errors_are_retried(env, monkeypatch):
    tmp, cfg = env
    real, calls = plugins.DatedFileSource.fetch, []

    def flaky(self, path):
        calls.append(path.name)
        if calls.count(path.name) == 1:
            raise ConnectionError("blip")
        return real(self, path)

    monkeypatch.setattr(plugins.DatedFileSource, "fetch", flaky)
    assert go(cfg)["status"] == "success"
    assert len(calls) == 12  # every file failed once, then succeeded


def test_exhausted_retries_fail_run_but_keep_going(env, monkeypatch):
    tmp, cfg = env
    real = plugins.DatedFileSource.fetch

    def dead_on_13(self, path):
        if "10-13" in path.name:
            raise TimeoutError("down")
        return real(self, path)

    monkeypatch.setattr(plugins.DatedFileSource, "fetch", dead_on_13)
    rep = go(cfg)
    assert rep["status"] == "failed" and "orders_2026-10-13.csv" in rep["errors"][0]
    assert len(rep["files"]) == 5
    monkeypatch.setattr(plugins.DatedFileSource, "fetch", real)
    assert [f["file"] for f in go(cfg)["files"]] == ["orders_2026-10-13.csv"]


def test_crash_mid_file_commits_nothing(env, monkeypatch):
    tmp, cfg = env
    real = plugins.PartitionedJsonlSink.write

    def crash(self, records):
        if self.batch.endswith("10-13"):
            for i, _ in enumerate(records):
                if i == 5:
                    raise RuntimeError("power cut")
        return real(self, records)

    monkeypatch.setattr(plugins.PartitionedJsonlSink, "write", crash)
    with pytest.raises(RuntimeError):
        go(cfg)
    state = json.loads((tmp / "state").read_text(encoding="utf-8"))
    assert state["watermark"] == "2026-10-12"
    assert not list((tmp / "out").rglob("orders_2026-10-13.jsonl*"))
    monkeypatch.setattr(plugins.PartitionedJsonlSink, "write", real)
    assert go(cfg)["files"][0]["file"] == "orders_2026-10-13.csv"


def test_error_level_check_fails_run(env):
    tmp, cfg = env
    cfg["checks"] = [{"type": "in_range", "column": "amount", "low": 0, "high": 100000}]
    rep = go(cfg)
    assert rep["status"] == "failed" and not rep["quality"]["passed"]


def test_cli_exit_codes(env, tmp_path, capsys):
    tmp, cfg = env
    p = tmp / "c.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    assert main(["run", str(p)]) == 0
    assert "status=success" in capsys.readouterr().out
    cfg["transforms"][3].pop("key")
    p.write_text(json.dumps(cfg), encoding="utf-8")
    assert main(["run", str(p)]) == 2
    assert "transforms[3].key" in capsys.readouterr().err


def test_config_must_have_paths_and_incremental_source(env):
    tmp, cfg = env
    with pytest.raises(ConfigError, match="^state"):
        go({**cfg, "state": None})
    with pytest.raises(ConfigError, match="^source.type"):
        go({**cfg, "source": {"type": "csv", "path": "x.csv"}})


def test_empty_incoming_folder(env):
    tmp, cfg = env
    cfg["source"]["path"] = str(tmp / "nothing_here")
    assert go(cfg)["status"] == "nothing_to_do"
