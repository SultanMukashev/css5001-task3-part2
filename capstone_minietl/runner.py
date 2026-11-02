"""minietl runner: incremental, idempotent, quarantining, retrying, partitioned, checked."""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from capstone_minietl import plugins  # noqa: F401  (registers minietl plugins)
from d1_4_incremental_loader.solution import atomic_write_json
from d1_5_retry.solution import RetryExhausted, retry
from d2_6_registry.solution import ConfigError, build, load_config


def _now() -> datetime:
    return datetime.now(UTC)


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"watermark": None, "files": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)


def run(config, clock: Callable[[], datetime] = _now,
        sleep: Callable[[float], None] = time.sleep) -> dict:
    started = clock()
    cfg = load_config(config) if isinstance(config, (str, Path)) else config
    for key in ("state", "quarantine", "reports"):
        if not isinstance(cfg.get(key), str):
            raise ConfigError(f"{key}: missing path")
    built = build(cfg)
    source, sink, pipeline = built.pipeline.source, built.sink, built.pipeline
    if not hasattr(source, "list_files"):
        raise ConfigError("source.type: minietl needs an incremental source such as 'dated_files'")
    built.suite.clock = clock
    rcfg = cfg.get("retry", {})
    fetch = retry(max_attempts=rcfg.get("max_attempts", 3), base=rcfg.get("base", 0.5),
                  sleep=sleep)(source.fetch)

    state_path = Path(cfg["state"])
    state = _load_state(state_path)
    watermark = date.fromisoformat(state["watermark"]) if state["watermark"] else None
    steps = {"source": {"rows_in": 0, "rows_out": 0, "rejected": 0}}
    steps.update({t.name: {"rows_in": 0, "rows_out": 0, "rejected": 0} for t in pipeline.transforms})
    steps["sink"] = {"rows_in": 0, "rows_out": 0, "rejected": 0}
    files, errors, loaded = [], [], []

    for day, path in source.list_files():
        try:
            data = fetch(path)
        except RetryExhausted as exc:
            errors.append(f"{path.name}: {exc} (last error: {exc.__cause__!r})")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if state["files"].get(path.name) == digest:
            continue  # already loaded this exact content -> idempotent re-run

        source.rejects.clear()
        sink.rejected.clear()
        sink.batch = path.stem
        records, stats = pipeline.process(source.parse(path.name, data), reset=not files)
        batch: list[dict] = []  # copy of what reaches the sink, for the quality suite

        def tee(rows):
            for r in rows:
                batch.append(r)
                yield r

        with sink:
            written = sink.write(tee(records))
        rejects = source.rejects + stats.rejects + sink.rejected
        _write_jsonl(Path(cfg["quarantine"]) / f"{path.stem}.jsonl",
                     [{"reason": f"{r['step']}: {r['error']}", "record": r["record"]} for r in rejects])

        steps["source"]["rows_out"] += stats.read
        steps["source"]["rows_in"] += stats.read + len(source.rejects)
        steps["source"]["rejected"] += len(source.rejects)
        for st in stats.steps:
            for k in ("rows_in", "rows_out", "rejected"):
                steps[st.name][k] += getattr(st, k)
        steps["sink"]["rows_in"] += len(batch)
        steps["sink"]["rows_out"] += written
        steps["sink"]["rejected"] += len(sink.rejected)
        loaded.extend(batch)

        late = watermark is not None and day < watermark
        files.append({"file": path.name, "late": late, "written": written, "rejected": len(rejects)})
        state["files"][path.name] = digest
        watermark = max(watermark, day) if watermark else day
        state["watermark"] = watermark.isoformat()
        atomic_write_json(state_path, state)  # only after the file is fully committed

    quality = built.suite.run(loaded) if files else None
    failed = bool(errors) or (quality is not None and not quality.passed)
    ended = clock()
    report = {
        "status": "failed" if failed else ("success" if files else "nothing_to_do"),
        "started_at": started.astimezone(UTC).isoformat(),
        "ended_at": ended.astimezone(UTC).isoformat(),
        "duration_seconds": round((ended - started).total_seconds(), 3),
        "watermark": state["watermark"],
        "files": files,
        "errors": errors,
        "steps": [{"step": name, **counts} for name, counts in steps.items()],
        "quality": None if quality is None else {
            "passed": quality.passed,
            "results": [vars(r) for r in quality.results],
        },
    }
    report_path = Path(cfg["reports"]) / f"run_{started.astimezone(UTC):%Y%m%dT%H%M%S%fZ}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    report["report_path"] = str(report_path)
    return report
