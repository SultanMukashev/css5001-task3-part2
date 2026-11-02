from d1_6_sessions.solution import sessionise, sessionise_file


def ev(user, ts, url="/"):
    return {"user_id": user, "timestamp": ts, "url": url}


def test_out_of_order_mixed_zones():
    events = [
        ev("u1", "2026-10-01T10:40:00+00:00"),
        ev("u1", "2026-10-01T15:00:00+05:00"),   # 10:00 UTC
        ev("u1", "2026-10-01T10:20:00Z"),
        ev("u1", "2026-10-01T11:20:00Z"),        # 40 min gap -> new session
        ev("u2", "2026-10-01T10:00:00Z"),
    ]
    sessions, rejected = sessionise(events)
    assert rejected == []
    u1 = [s for s in sessions if s.user_id == "u1"]
    assert [(s.page_count, s.duration_seconds) for s in u1] == [(3, 2400), (1, 0)]
    assert u1[0].start == "2026-10-01T10:00:00+00:00"


def test_exactly_thirty_minutes_stays_in_session():
    sessions, _ = sessionise([ev("u", "2026-10-01T10:00Z"), ev("u", "2026-10-01T10:30Z")])
    assert len(sessions) == 1


def test_crosses_midnight():
    sessions, _ = sessionise([ev("u", "2026-10-31T23:50Z"), ev("u", "2026-11-01T00:10Z")])
    assert len(sessions) == 1 and sessions[0].duration_seconds == 1200


def test_naive_times_use_source_tz():
    sessions, _ = sessionise([ev("u", "2026-10-01T09:00")], source_tz="Asia/Tokyo")
    assert sessions[0].start == "2026-10-01T00:00:00+00:00"


def test_bad_events_rejected_not_crashing():
    sessions, rejected = sessionise([ev("u", "nope"), ev("", "2026-10-01T10:00Z"),
                                     {"timestamp": None}, ev("u", "2026-10-01T10:00Z")])
    assert len(sessions) == 1 and len(rejected) == 3
    assert sessionise([]) == ([], [])


def test_file_roundtrip(tmp_path):
    src = tmp_path / "clicks.csv"
    src.write_text("user_id,timestamp,url\nu,2026-10-01T10:00Z,/a\nu,bad,/b\n", encoding="utf-8")
    assert sessionise_file(src, tmp_path / "s.csv") == {"sessions": 1, "rejected": 1}
    assert (tmp_path / "s.csv").read_text(encoding="utf-8").startswith("user_id,start,end")
