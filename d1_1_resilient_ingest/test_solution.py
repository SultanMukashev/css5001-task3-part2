import csv
import shutil
from pathlib import Path

import pytest

from d1_1_resilient_ingest.solution import (
    InvalidAmount, ingest, parse_amount,
)

SAMPLE = Path(__file__).parents[1] / "data" / "orders.csv"


def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_sample(tmp_path, capsys):
    s = ingest(SAMPLE, tmp_path)
    assert (s.read, s.accepted, s.rejected) == (5, 2, 3)
    assert [r["order_id"] for r in read(tmp_path / "clean.csv")] == ["1001", "1002"]
    reasons = {r["order_id"]: r["reason"] for r in read(tmp_path / "rejects.csv")}
    assert reasons["1003"].startswith("InvalidAmount")
    assert reasons["1004"].startswith("MissingField: missing customer_email")
    assert reasons["1001"].startswith("DuplicateKey")
    assert dict(s.by_reason) == {"InvalidAmount": 1, "MissingField": 1, "DuplicateKey": 1}
    assert "rejected=3" in capsys.readouterr().out


@pytest.mark.parametrize("raw", ["abc", "-1", "NaN", "Infinity", ""])
def test_bad_amounts(raw):
    with pytest.raises(InvalidAmount):
        parse_amount(raw)


def test_decimal_not_float():
    assert parse_amount("0.10") + parse_amount("0.20") == parse_amount("0.30")


def test_malformed_lines(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text(
        "order_id,customer_email,phone,amount,currency,order_date\n"
        "1,a@b.co,1,1.00,USD,2026-10-01,EXTRA\n"   # too many cells
        "2,a@b.co\n"                                # too few
        "\n"                                        # blank line: skipped by csv
        "3,a@b.co,1,1.00,USD,2026-10-01\n",
        encoding="utf-8",
    )
    s = ingest(p, tmp_path)
    assert (s.accepted, s.rejected) == (1, 2)
    assert s.by_reason == {"MalformedRow": 1, "MissingField": 1}


def test_empty_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    s = ingest(p, tmp_path)
    assert (s.read, s.accepted, s.rejected) == (0, 0, 0)
    assert read(tmp_path / "clean.csv") == []


def test_fallback_encoding(tmp_path, capsys):
    p = tmp_path / "cp.csv"
    p.write_bytes("order_id,customer_email,phone,amount,currency,order_date\n"
                  "7,айгерим@пример.kz,1,5.00,KZT,2026-10-01\n".encode("cp1251"))
    s = ingest(p, tmp_path, fallback_encoding="cp1251")
    assert s.accepted == 1
    assert read(tmp_path / "clean.csv")[0]["customer_email"] == "айгерим@пример.kz"
    assert "not valid UTF-8" in capsys.readouterr().err


def test_bom_is_tolerated(tmp_path):
    p = tmp_path / "bom.csv"
    shutil.copy(SAMPLE, p)
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    assert ingest(p, tmp_path).accepted == 2
