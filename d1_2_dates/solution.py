"""D1.2 Date normalisation and partition keys."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class InvalidDate(ValueError):
    pass


# Slash/dot dates with an optional time. Order of day/month decided by `dayfirst`.
_NUMERIC = re.compile(
    r"(\d{1,2})([./])(\d{1,2})\2(\d{4})"
    r"(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)


def _parse_naive_or_aware(text: str, dayfirst: bool) -> datetime:
    m = _NUMERIC.fullmatch(text)
    if m:
        a, sep, b, year, hh, mm, ss = m.groups()
        # Dots (DD.MM.YYYY) are always day-first; slashes follow the flag.
        day, month = (a, b) if (dayfirst or sep == ".") else (b, a)
        return datetime(int(year), int(month), int(day),
                        int(hh or 0), int(mm or 0), int(ss or 0))
    return datetime.fromisoformat(text)  # ISO 8601, incl. offsets and "Z"


def parse_ts(value, source_tz: str = "UTC", dayfirst: bool = True) -> datetime:
    """Parse any supported format to an aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    else:
        if not isinstance(value, str) or not value.strip():
            raise InvalidDate(f"empty or non-text date: {value!r}")
        try:
            dt = _parse_naive_or_aware(value.strip(), dayfirst)
        except ValueError as exc:
            raise InvalidDate(f"cannot parse date {value!r}: {exc}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        tz = ZoneInfo(source_tz)
        local = dt.replace(tzinfo=tz)  # fold=0: ambiguous times take the earlier offset
        if local.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != dt:
            raise InvalidDate(f"{value!r} does not exist in {source_tz} (DST gap)")
        dt = local
    return dt.astimezone(UTC)


def normalise_ts(value, source_tz: str, dayfirst: bool = True) -> str:
    return parse_ts(value, source_tz, dayfirst).isoformat()


def partition_path(ts) -> str:
    dt = parse_ts(ts)
    return f"year={dt.year:04d}/month={dt.month:02d}/day={dt.day:02d}"


def write_partitioned(records, out_dir, ts_field: str, source_tz: str,
                      dayfirst: bool = True) -> dict:
    """Write each record to out_dir/<partition>/records.jsonl (overwrite = re-runnable).

    Returns {"written": n, "rejected": [(record, reason), ...]}.
    """
    groups: dict[str, list[dict]] = {}
    rejected = []
    for record in records:
        try:
            ts = normalise_ts(record.get(ts_field), source_tz, dayfirst)
        except InvalidDate as exc:
            rejected.append((record, str(exc)))
            continue
        groups.setdefault(partition_path(ts), []).append({**record, ts_field: ts})
    # shortcut: groups held in memory, fine for one batch; stream per partition for big inputs
    for part, rows in groups.items():
        folder = Path(out_dir) / part
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "records.jsonl", "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"written": sum(map(len, groups.values())), "rejected": rejected}


if __name__ == "__main__":
    for raw in ["2026-10-01", "01/10/2026", "2026-10-02T14:30:00+02:00", "2026-13-01"]:
        try:
            print(raw, "->", normalise_ts(raw, "Asia/Almaty"))
        except InvalidDate as e:
            print(raw, "->", e)
