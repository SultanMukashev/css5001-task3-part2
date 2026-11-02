"""D1.4 Incremental loader with a watermark."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

FILE_RE = re.compile(r"events_(\d{4}-\d{2}-\d{2})\.jsonl")


def atomic_write_json(path: Path, data) -> None:
    """Write to a temp file in the same folder, fsync, then os.replace (atomic on POSIX/NTFS)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_watermark(state_path: Path) -> date | None:
    if not Path(state_path).exists():
        return None
    with open(state_path, encoding="utf-8") as f:
        value = json.load(f).get("watermark")
    return date.fromisoformat(value) if value else None


def pending_files(in_dir: Path, watermark: date | None) -> list[tuple[date, Path]]:
    found = []
    for p in Path(in_dir).iterdir():
        m = FILE_RE.fullmatch(p.name)
        if not m:
            log.info("ignoring %s: name does not match events_YYYY-MM-DD.jsonl", p.name)
            continue
        try:
            day = date.fromisoformat(m.group(1))
        except ValueError:
            log.warning("ignoring %s: impossible date in name", p.name)
            continue
        if watermark and day <= watermark:
            continue
        found.append((day, p))
    return sorted(found)


def process_file(src: Path, out_path: Path, transform: Callable[[dict], dict]) -> dict:
    stats = {"file": src.name, "lines": 0, "written": 0, "bad": 0}
    tmp = out_path.with_name(out_path.name + ".tmp")
    try:
        with open(src, "rb") as f, open(tmp, "w", encoding="utf-8") as out:
            for lineno, raw in enumerate(f, start=1):  # one line at a time
                stats["lines"] += 1
                try:
                    text = raw.decode("utf-8").strip()
                    if not text:
                        continue
                    record = json.loads(text)
                    if not isinstance(record, dict):
                        raise ValueError("line is JSON but not an object")
                except (UnicodeDecodeError, ValueError) as exc:  # JSONDecodeError is a ValueError
                    stats["bad"] += 1
                    log.warning("%s:%d skipped: %s", src.name, lineno, exc)
                    continue
                out.write(json.dumps(transform(record), ensure_ascii=False) + "\n")
                stats["written"] += 1
        os.replace(tmp, out_path)  # output appears only when the whole file is done
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return stats


def run(in_dir, out_dir, state_path="watermark.json",
        transform: Callable[[dict], dict] = lambda r: r) -> list[dict]:
    out_dir, state_path = Path(out_dir), Path(state_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for day, src in pending_files(Path(in_dir), read_watermark(state_path)):
        results.append(process_file(src, out_dir / src.name, transform))
        atomic_write_json(state_path, {"watermark": day.isoformat()})  # only after success
        log.info("processed %s, watermark -> %s", src.name, day)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    in_dir, out_dir = sys.argv[1:3] if len(sys.argv) >= 3 else ("incoming", "processed")
    print(run(in_dir, out_dir, Path(out_dir) / "watermark.json"))
