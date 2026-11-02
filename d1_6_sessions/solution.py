"""D1.6 Clickstream sessionisation."""
from __future__ import annotations

import csv
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from d1_2_dates.solution import InvalidDate, parse_ts

GAP = timedelta(minutes=30)


@dataclass
class Session:
    user_id: str
    start: str
    end: str
    duration_seconds: int
    page_count: int


def _session(user: str, events: list[datetime]) -> Session:
    return Session(user, events[0].isoformat(), events[-1].isoformat(),
                   int((events[-1] - events[0]).total_seconds()), len(events))


def sessionise(events, source_tz: str = "UTC", gap: timedelta = GAP):
    """Return (sessions, rejected). A gap strictly longer than `gap` starts a new session."""
    per_user: dict[str, list[datetime]] = {}
    rejected = []
    for e in events:
        try:
            user = (e.get("user_id") or "").strip()
            if not user:
                raise ValueError("missing user_id")
            per_user.setdefault(user, []).append(parse_ts(e.get("timestamp"), source_tz))
        except ValueError as exc:  # InvalidDate is a ValueError
            rejected.append((e, str(exc)))
    sessions = []
    for user, times in sorted(per_user.items()):
        times.sort()  # events arrive out of order
        current = [times[0]]
        for t in times[1:]:
            if t - current[-1] > gap:
                sessions.append(_session(user, current))
                current = []
            current.append(t)
        sessions.append(_session(user, current))
    return sessions, rejected


def sessionise_file(in_path, out_path, source_tz: str = "UTC") -> dict:
    with open(in_path, encoding="utf-8", newline="") as f:
        sessions, rejected = sessionise(csv.DictReader(f), source_tz)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(Session.__dataclass_fields__))
        w.writeheader()
        w.writerows(asdict(s) for s in sessions)
    return {"sessions": len(sessions), "rejected": len(rejected)}


if __name__ == "__main__":
    print(sessionise_file(sys.argv[1], sys.argv[2], *sys.argv[3:4]))
