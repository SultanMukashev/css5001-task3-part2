import csv
from pathlib import Path

import pytest

from d1_3_text_cleaning.solution import (
    InvalidPhone, export_analytics, is_valid_email, mask_email, mask_phone,
    normalise_phone, strip_html,
)

SAMPLE = Path(__file__).parents[1] / "data" / "orders.csv"


@pytest.mark.parametrize("raw,expected", [
    ("+7 701 123 4567", "+7-701-123-4567"),
    ("8(701)1234568", "+7-701-123-4568"),
    ("7011234569", "+7-701-123-4569"),
    ("+7-701-123-4570", "+7-701-123-4570"),
])
def test_phones(raw, expected):
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "+1 202 555 0100 99", None])
def test_bad_phones(raw):
    with pytest.raises(InvalidPhone):
        normalise_phone(raw)


def test_emails():
    assert is_valid_email("aru@example.com")
    assert is_valid_email("a.b+tag@mail.example.kz")
    for bad in ["dana@example", "", "@x.com", "a@@b.com", "a b@c.com"]:
        assert not is_valid_email(bad)


def test_masking():
    assert mask_email("aru@example.com") == "a***@example.com"
    assert mask_phone("+7-701-123-4567") == "+*-***-***-4567"
    assert mask_phone("") == ""


def test_strip_html():
    assert strip_html("<p>Big&nbsp;<b>sale</b></p><br/>now") == "Big sale now"
    assert strip_html("") == ""


def test_export_sample(tmp_path):
    stats = export_analytics(SAMPLE, tmp_path / "a.csv")
    assert stats["written"] == 5 and stats["rejected"] == []
    with open(tmp_path / "a.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["customer_email"] == "a***@example.com"
    assert rows[1]["email_valid"] == "false"
    assert all(r["phone"].endswith(("4567", "4568", "4569", "4570")) for r in rows)
    assert all("701" not in r["phone"] for r in rows)
