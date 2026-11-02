"""Generate a week of synthetic, deliberately dirty order and click files.

python -m capstone_minietl.make_sample_data [OUT_DIR]

Writes OUT_DIR/incoming/{orders,clicks}/ and OUT_DIR/late/orders_2026-10-14.csv
(the late-arriving file: move it into incoming/orders after the first run).
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DAYS = [date(2026, 10, 12) + timedelta(days=i) for i in range(7)]
LATE_DAY = date(2026, 10, 14)
CORRUPT_DAY = date(2026, 10, 15)
ZONES = [timezone.utc, timezone(timedelta(hours=5)), timezone(timedelta(hours=9)),
         timezone(timedelta(hours=-4))]


def order_rows(day: date, rng: random.Random, start_id: int) -> list[list[str]]:
    rows = []
    for i in range(40):
        oid = start_id + i
        local = datetime(day.year, day.month, day.day, rng.randrange(24), rng.randrange(60))
        style = rng.randrange(4)
        if style == 0:
            ts = local.isoformat()                          # naive -> Asia/Almaty
        elif style == 1:
            ts = local.strftime("%d/%m/%Y %H:%M")          # day-first, naive
        else:
            ts = local.replace(tzinfo=rng.choice(ZONES)).isoformat()  # explicit offset
        rows.append([str(oid), f"user{oid}@example.com", f"{rng.uniform(1, 500):.2f}",
                     rng.choice(["USD", "KZT", "EUR"]), ts])
    # dirty rows
    rows.append([str(start_id + 90), "", "10.00", "USD", f"{day}T10:00"])          # missing email
    rows.append([str(start_id + 91), "x@example.com", "abc", "USD", f"{day}T10:00"])  # bad amount
    rows.append([str(start_id + 92), "y@example.com", "5.00", "USD", f"{day.year}-13-01"])  # bad date
    rows.append(rows[0][:])                                                        # duplicate id
    rows.append([str(start_id + 93), "z@example.com", "-3.00", "usd", f"{day}T11:00"])  # neg + lower ccy
    rows.append([str(start_id + 94), "short@example.com"])                         # too few fields
    return rows


def click_lines(day: date, rng: random.Random) -> list[str]:
    lines = []
    for _ in range(60):
        ts = datetime(day.year, day.month, day.day, rng.randrange(24), rng.randrange(60),
                      tzinfo=rng.choice(ZONES))
        lines.append(json.dumps({"user_id": f"u{rng.randrange(10)}", "timestamp": ts.isoformat(),
                                 "url": rng.choice(["/", "/cart", "/item/1", "/item/2", "/pay"])}))
    lines += ['{"user_id": "u1", "timestamp": "yesterday", "url": "/"}', "{not json", "[1, 2, 3]"]
    return lines


def generate(out: Path) -> None:
    rng = random.Random(7)
    orders, clicks, late = out / "incoming" / "orders", out / "incoming" / "clicks", out / "late"
    for d in (orders, clicks, late):
        d.mkdir(parents=True, exist_ok=True)
    header = ["order_id", "customer_email", "amount", "currency", "order_date"]
    for n, day in enumerate(DAYS):
        target = (late if day == LATE_DAY else orders) / f"orders_{day}.csv"
        with open(target, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(order_rows(day, rng, 10_000 + n * 100))
        if day == CORRUPT_DAY:  # corrupt: invalid UTF-8 bytes and a truncated tail
            target.write_bytes(target.read_bytes()[:900] + b"\xff\xfe\x00garbage\x9d\n1234,\x80\x81")
        (clicks / f"clicks_{day}.jsonl").write_text("\n".join(click_lines(day, rng)) + "\n", encoding="utf-8")
    (orders / "README.txt").write_text("not a data file; should be ignored\n", encoding="utf-8")


if __name__ == "__main__":
    generate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data")
