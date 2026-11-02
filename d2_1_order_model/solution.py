"""D2.1 Typed record model."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from d1_2_dates.solution import parse_ts

CURRENCY = re.compile(r"[A-Z]{3}")


class OrderError(ValueError):
    pass


@dataclass(frozen=True)
class Order:
    order_id: int
    email: str
    amount: Decimal
    currency: str
    ordered_at: datetime

    def __post_init__(self):
        if not isinstance(self.order_id, int) or isinstance(self.order_id, bool):
            raise OrderError(f"order_id must be int, got {self.order_id!r}")
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite() or self.amount <= 0:
            raise OrderError(f"amount must be a positive Decimal, got {self.amount!r}")
        if not isinstance(self.currency, str) or not CURRENCY.fullmatch(self.currency):
            raise OrderError(f"currency must be 3 uppercase letters, got {self.currency!r}")
        if not isinstance(self.ordered_at, datetime) or self.ordered_at.utcoffset() is None:
            raise OrderError(f"ordered_at must be timezone-aware, got {self.ordered_at!r}")
        # frozen: bypass __setattr__ once to store the UTC form
        object.__setattr__(self, "ordered_at", self.ordered_at.astimezone(UTC))

    @classmethod
    def from_row(cls, row: dict, source_tz: str = "UTC") -> Order:
        try:
            return cls(
                order_id=int(row["order_id"]),
                email=row["email"].strip(),
                amount=Decimal(row["amount"]),
                currency=row["currency"].strip(),
                ordered_at=parse_ts(row["ordered_at"], source_tz),
            )
        except KeyError as exc:
            raise OrderError(f"missing field {exc}") from exc
        except OrderError:
            raise
        except (InvalidOperation, ValueError, AttributeError) as exc:
            raise OrderError(f"bad row {row!r}: {exc}") from exc

    def to_row(self) -> dict[str, str]:
        return {
            "order_id": str(self.order_id),
            "email": self.email,
            "amount": str(self.amount),
            "currency": self.currency,
            "ordered_at": self.ordered_at.isoformat(),
        }
