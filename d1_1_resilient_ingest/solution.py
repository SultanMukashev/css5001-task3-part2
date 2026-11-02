"""D1.1 Resilient CSV ingestion with a quarantine."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED = ("order_id", "customer_email", "phone", "amount", "currency", "order_date")


class ValidationError(Exception):
    """Base class for one bad row. Caught per row, never stops the run."""


class MissingField(ValidationError):
    pass


class InvalidAmount(ValidationError):
    pass


class DuplicateKey(ValidationError):
    pass


class MalformedRow(ValidationError):
    pass


@dataclass
class Summary:
    read: int = 0
    accepted: int = 0
    rejected: int = 0
    by_reason: Counter = field(default_factory=Counter)

    def __str__(self) -> str:
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(self.by_reason.items())) or "none"
        return (f"rows read={self.read} accepted={self.accepted} "
                f"rejected={self.rejected} (by reason: {reasons})")


def parse_amount(raw: str) -> Decimal:
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidAmount(f"amount {raw!r} is not a number") from exc
    if not amount.is_finite():
        raise InvalidAmount(f"amount {raw!r} is not finite")
    if amount < 0:
        raise InvalidAmount(f"amount {raw!r} is negative")
    return amount


def validate(row: dict, seen: set[str]) -> None:
    if None in row:  # DictReader puts surplus cells under the None key
        raise MalformedRow(f"{len(row[None])} unexpected extra field(s)")
    for name in REQUIRED:
        value = row.get(name)
        if value is None or not value.strip():
            raise MissingField(f"missing {name}")
    parse_amount(row["amount"].strip())
    key = row["order_id"].strip()
    if key in seen:
        raise DuplicateKey(f"order_id {key} already accepted")


def detect_encoding(path: Path, fallback: str) -> str:
    """Decode the whole file once (streaming) so we never write half a run."""
    try:
        with open(path, encoding="utf-8-sig") as f:  # -sig: tolerate an Excel BOM
            for _ in f:
                pass
        return "utf-8-sig"
    except UnicodeDecodeError:
        print(f"warning: {path} is not valid UTF-8, retrying as {fallback}", file=sys.stderr)
        return fallback


def ingest(path, out_dir=None, fallback_encoding: str = "cp1251") -> Summary:
    path = Path(path)
    out_dir = Path(out_dir) if out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = detect_encoding(path, fallback_encoding)
    summary, seen = Summary(), set()

    with open(path, encoding=encoding, newline="") as src, \
         open(out_dir / "clean.csv", "w", encoding="utf-8", newline="") as good_f, \
         open(out_dir / "rejects.csv", "w", encoding="utf-8", newline="") as bad_f:
        reader = csv.DictReader(src)
        columns = list(reader.fieldnames or REQUIRED)
        good = csv.DictWriter(good_f, columns, extrasaction="ignore")
        bad = csv.DictWriter(bad_f, columns + ["reason"], extrasaction="ignore", restval="")
        good.writeheader()
        bad.writeheader()
        for row in reader:
            summary.read += 1
            try:
                validate(row, seen)
            except ValidationError as exc:
                summary.rejected += 1
                summary.by_reason[type(exc).__name__] += 1
                bad.writerow({**row, "reason": f"{type(exc).__name__}: {exc}"})
            else:
                seen.add(row["order_id"].strip())
                summary.accepted += 1
                good.writerow(row)
    print(summary)
    return summary


if __name__ == "__main__":
    ingest(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "orders.csv")
