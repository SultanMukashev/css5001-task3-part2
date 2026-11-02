import json
from pathlib import Path

import pytest

from d2_2_sources_sinks.solution import Source
from d2_6_registry.solution import ConfigError, Registered, build, load_config

SAMPLE = str(Path(__file__).parents[1] / "data" / "orders.csv")


def config(tmp_path, **over):
    cfg = {
        "source": {"type": "csv", "path": SAMPLE},
        "transforms": [{"type": "cast", "schema": "orders"}, {"type": "dedupe", "key": "order_id"}],
        "checks": [{"type": "not_null", "column": "customer_email"}],
        "sink": {"type": "jsonl", "path": str(tmp_path / "out" / "orders.jsonl")},
    }
    cfg.update(over)
    return cfg


def test_builds_and_runs(tmp_path):
    stats, report = build(config(tmp_path)).run()
    assert (stats.read, stats.written, len(stats.rejects)) == (5, 3, 1)
    assert [s.name for s in stats.steps] == ["Cast", "Deduplicate"]
    assert not report.passed  # order 1004 has no email
    assert report.results[0].failed_count == 1
    assert len((tmp_path / "out" / "orders.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_registry_is_populated_by_init_subclass():
    assert {"csv", "jsonl"} <= set(Registered.registry["source"])
    assert issubclass(Registered.registry["source"]["csv"], Source)
    with pytest.raises(TypeError, match="already registered"):
        class Dup(Registered, kind="source", name="csv"):
            pass


@pytest.mark.parametrize("change,path", [
    ({"transforms": [{"type": "cast", "schema": "orders"}, {"type": "dedupe"}]}, "transforms[1].key"),
    ({"transforms": [{"type": "explode"}]}, "transforms[0].type"),
    ({"transforms": [{"type": "cast", "schema": "nope"}]}, "transforms[0].schema"),
    ({"transforms": [{"type": "dedupe", "key": "id", "colour": "red"}]}, "transforms[0].colour"),
    ({"checks": [{"type": "in_range", "column": "amount", "low": 0}]}, "checks[0].high"),
    ({"checks": [{"type": "not_null", "column": "a", "severity": "fatal"}]}, "checks[0]:"),
    ({"source": {"path": "x"}}, "source.type"),
    ({"sink": "jsonl"}, "sink:"),
    ({"transforms": {"type": "cast"}}, "transforms:"),
])
def test_config_errors_name_exact_path(tmp_path, change, path):
    with pytest.raises(ConfigError) as e:
        build(config(tmp_path, **change))
    assert str(e.value).startswith(path)


def test_missing_top_level_and_bad_json(tmp_path):
    cfg = config(tmp_path)
    del cfg["sink"]
    with pytest.raises(ConfigError, match="^sink: missing"):
        build(cfg)
    p = tmp_path / "c.json"
    p.write_text("{oops", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(p)
    p.write_text(json.dumps(config(tmp_path)), encoding="utf-8")
    assert build(load_config(p)).run()[0].written == 3
