import json

import pytest

from d1_2_dates.solution import (
    InvalidDate, normalise_ts, parse_ts, partition_path, write_partitioned,
)


def test_sample_formats():
    assert normalise_ts("2026-10-01", "UTC") == "2026-10-01T00:00:00+00:00"
    assert normalise_ts("2026-10-02T14:30:00+02:00", "Asia/Tokyo") == "2026-10-02T12:30:00+00:00"
    assert normalise_ts("2026-10-02T12:30:00Z", "Asia/Tokyo") == "2026-10-02T12:30:00+00:00"
    assert normalise_ts("01.10.2026 10:00", "UTC") == "2026-10-01T10:00:00+00:00"


def test_dayfirst_flag():
    assert normalise_ts("01/10/2026", "UTC", dayfirst=True).startswith("2026-10-01")
    assert normalise_ts("01/10/2026", "UTC", dayfirst=False).startswith("2026-01-10")


@pytest.mark.parametrize("bad", ["2026-13-01", "31/02/2026", "abc", "", None, "2026-10-01T25:00"])
def test_invalid_dates_keep_original_value(bad):
    with pytest.raises(InvalidDate) as e:
        normalise_ts(bad, "UTC")
    assert repr(bad) in str(e.value)


def test_tokyo_partitions():  # the "Done when" case
    assert partition_path(normalise_ts("2026-10-31 23:30", "Asia/Tokyo", dayfirst=False)) \
        == "year=2026/month=10/day=31"
    assert normalise_ts("2026-11-01T01:30", "Asia/Tokyo") == "2026-10-31T16:30:00+00:00"
    assert partition_path(normalise_ts("2026-11-01T01:30", "Asia/Tokyo")) == "year=2026/month=10/day=31"


def test_year_rollover():
    ts = normalise_ts("2026-12-31T23:30", "America/New_York")
    assert partition_path(ts) == "year=2027/month=01/day=01"


def test_dst_ambiguous_takes_earlier_offset():
    # 02:30 happens twice in Berlin on 25 Oct 2026; first time is CEST (+02:00)
    assert normalise_ts("2026-10-25T02:30", "Europe/Berlin") == "2026-10-25T00:30:00+00:00"


def test_dst_gap_is_invalid():
    with pytest.raises(InvalidDate, match="DST gap"):
        normalise_ts("2026-03-29T02:30", "Europe/Berlin")


def test_offset_values_ignore_source_tz():
    assert parse_ts("2026-10-01T00:00:00+05:00", "America/New_York").hour == 19


def test_write_partitioned(tmp_path):
    recs = [{"id": 1, "ts": "2026-11-01T01:30"}, {"id": 2, "ts": "2026-13-01"},
            {"id": 3, "ts": "2026-11-01T10:00"}]
    res = write_partitioned(recs, tmp_path, "ts", "Asia/Tokyo")
    assert res["written"] == 2 and len(res["rejected"]) == 1
    oct31 = (tmp_path / "year=2026/month=10/day=31/records.jsonl").read_text(encoding="utf-8")
    assert json.loads(oct31)["id"] == 1
    assert (tmp_path / "year=2026/month=11/day=01/records.jsonl").exists()
    assert write_partitioned([], tmp_path, "ts", "UTC")["written"] == 0
