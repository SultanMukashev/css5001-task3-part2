"""D1.3 Text cleaning and PII masking with regex."""
from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path


class InvalidPhone(ValueError):
    pass


NON_DIGIT = re.compile(r"\D")
KZ_PHONE = re.compile(r"7(\d{3})(\d{3})(\d{4})")
# Pragmatic, not RFC 5322: local@domain.tld with a 2+ letter TLD.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
TAG = re.compile(r"<[^>]*>")
SPACES = re.compile(r"\s+")


def normalise_phone(raw: str) -> str:
    digits = NON_DIGIT.sub("", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:  # local number without country code
        digits = "7" + digits
    if not KZ_PHONE.fullmatch(digits):
        raise InvalidPhone(f"cannot normalise phone {raw!r}")
    return KZ_PHONE.sub(r"+7-\1-\2-\3", digits)


def is_valid_email(email: str) -> bool:
    return bool(email) and EMAIL.fullmatch(email.strip()) is not None


def mask_email(email: str) -> str:
    # keep first char of the local part, hide the rest
    return re.sub(r"^([^@])[^@]*(@.+)$", lambda m: f"{m.group(1)}***{m.group(2)}", email)


def mask_phone(phone: str) -> str:
    # every digit that still has 4 digits after it becomes "*"
    return re.sub(r"\d(?=(?:\D*\d){4})", lambda m: "*", phone)


def strip_html(text: str) -> str:
    return SPACES.sub(" ", html.unescape(TAG.sub(" ", text or ""))).strip()


def clean_row(row: dict) -> dict:
    """Analytics export row. Raises InvalidPhone for an unusable phone."""
    out = dict(row)
    email = (row.get("customer_email") or "").strip()
    out["email_valid"] = str(is_valid_email(email)).lower()
    out["customer_email"] = mask_email(email)
    out["phone"] = mask_phone(normalise_phone(row.get("phone", "")))
    if "description" in row:
        out["description"] = strip_html(row["description"])
    return out


def export_analytics(in_path, out_path) -> dict:
    stats = {"read": 0, "written": 0, "rejected": []}
    with open(in_path, encoding="utf-8", newline="") as src, \
         open(out_path, "w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        writer = None
        for row in reader:
            stats["read"] += 1
            try:
                cleaned = clean_row(row)
            except InvalidPhone as exc:
                stats["rejected"].append((row, str(exc)))
                continue
            if writer is None:
                writer = csv.DictWriter(dst, list(cleaned), extrasaction="ignore")
                writer.writeheader()
            writer.writerow(cleaned)
            stats["written"] += 1
    return stats


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "orders.csv"
    print(export_analytics(src, "analytics.csv"))
