from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from d2_1_order_model.solution import Order, OrderError

ROW = {"order_id": "1001", "email": "aru@example.com", "amount": "120.50",
       "currency": "USD", "ordered_at": "2026-10-01T10:00:00+05:00"}


def test_from_row_and_round_trip():
    o = Order.from_row(ROW)
    assert o.amount == Decimal("120.50")
    assert o.ordered_at == datetime(2026, 10, 1, 5, tzinfo=UTC)
    assert o.ordered_at.tzinfo is UTC
    assert Order.from_row(o.to_row()) == o
    assert o.to_row()["amount"] == "120.50"


@pytest.mark.parametrize("amount", ["0.01", "1", "99999.999"])
@pytest.mark.parametrize("ts", ["2026-10-25T02:30", "2026-12-31T23:59:59", "01/10/2026"])
def test_round_trip_many(amount, ts):
    o = Order.from_row({**ROW, "amount": amount, "ordered_at": ts}, source_tz="Europe/Berlin")
    assert Order.from_row(o.to_row()) == o


@pytest.mark.parametrize("field,value", [
    ("amount", "0"), ("amount", "-5"), ("amount", "abc"), ("amount", "NaN"),
    ("currency", "usd"), ("currency", "US"), ("order_id", "x"), ("ordered_at", "2026-13-01"),
])
def test_invalid_rows(field, value):
    with pytest.raises(OrderError):
        Order.from_row({**ROW, field: value})


def test_missing_field():
    with pytest.raises(OrderError, match="missing field"):
        Order.from_row({k: v for k, v in ROW.items() if k != "email"})


def test_naive_datetime_rejected_and_frozen():
    with pytest.raises(OrderError):
        Order(1, "a@b.co", Decimal(1), "USD", datetime(2026, 1, 1))
    o = Order(1, "a@b.co", Decimal(1), "USD", datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3))))
    assert o.ordered_at.hour == 21
    with pytest.raises(FrozenInstanceError):
        o.amount = Decimal(2)
