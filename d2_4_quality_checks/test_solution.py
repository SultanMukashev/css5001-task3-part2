import json
from datetime import UTC, datetime, timedelta

import pytest

from d2_4_quality_checks.solution import (
    Check, Freshness, InRange, MatchesPattern, NotNull, QualitySuite, Unique,
)

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)
ROWS = [
    {"id": 1, "email": "a@x.com", "amount": "10", "ts": "2026-11-02T10:00:00Z"},
    {"id": 2, "email": "", "amount": "-1", "ts": "2026-11-01T10:00:00Z"},
    {"id": 2, "email": "bad", "amount": "abc", "ts": "nope"},
]


@pytest.mark.parametrize("check,failed", [
    (NotNull("email"), 1),
    (Unique("id"), 1),
    (InRange("amount", 0, 100), 2),
    (MatchesPattern("email", r"[^@]+@[^@]+\.\w+"), 2),
    (Freshness("ts", timedelta(hours=3)), 0),
])
def test_each_check(check, failed):
    res = check.run(ROWS, NOW)
    assert res.failed_count == failed and res.passed == (failed == 0)
    assert len(res.sample_failures) <= 5


def test_sample_capped_at_five():
    res = NotNull("x").run([{"x": None}] * 20)
    assert res.failed_count == 20 and len(res.sample_failures) == 5


def test_stale_and_empty_freshness():
    assert not Freshness("ts", timedelta(minutes=30)).run(ROWS, NOW).passed
    assert not Freshness("ts", timedelta(days=1)).run([], NOW).passed


def test_empty_input_row_checks_pass():
    for c in [NotNull("a"), Unique("a"), InRange("a", 0, 1), MatchesPattern("a", ".")]:
        assert c.run([]).passed


def test_unique_state_reset_between_runs():
    u = Unique("id")
    assert u.run([{"id": 1}]).passed and u.run([{"id": 1}]).passed


def test_severity_and_report(tmp_path):
    suite = QualitySuite([NotNull("email", severity="warning"), Unique("id", severity="warning")],
                         clock=lambda: NOW)
    report = suite.run(iter(ROWS))
    assert report.passed  # only warnings failed
    suite.write_report(report, tmp_path / "r" / "dq.json")
    data = json.loads((tmp_path / "r" / "dq.json").read_text(encoding="utf-8"))
    assert data["run_at"] == "2026-11-02T12:00:00+00:00"
    assert [r["passed"] for r in data["results"]] == [False, False]
    assert not QualitySuite([Unique("id")], clock=lambda: NOW).run(ROWS).passed


def test_crashing_check_is_reported():
    class Boom(Check):
        def is_bad(self, value):
            raise RuntimeError("bug")

    report = QualitySuite([Boom("id"), NotNull("id")]).run(ROWS)
    assert not report.passed and "crashed" in report.results[0].sample_failures[0]
    assert report.results[1].passed


def test_bad_severity():
    with pytest.raises(ValueError):
        NotNull("a", severity="fatal")
