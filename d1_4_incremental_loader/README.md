# D1.4 Incremental loader with a watermark

Run: `python -m d1_4_incremental_loader.solution IN_DIR OUT_DIR` (state in `OUT_DIR/watermark.json`).
API: `run(in_dir, out_dir, state_path, transform=identity)`.

- Files must match `events_YYYY-MM-DD.jsonl`; others (and impossible dates) are logged and ignored.
  Matching files newer than the watermark are processed in date order.
- Each file is read **line by line in binary** and decoded per line, so a bad byte or bad JSON only skips
  that line (logged as `file:line`). Non-object JSON lines are skipped too.
- Output is written to `OUT_DIR/<same name>.tmp` and `os.replace`d at the end → re-processing a file
  rewrites its output, never appends.
- The watermark (`{"watermark": "2026-10-17"}`) is written atomically (temp file in the same folder,
  `fsync`, `os.replace`) and only **after** the file's output is in place. A crash mid-file leaves the
  watermark and outputs untouched and removes the temp file; the next run redoes that file.

Known limits
- A late file (date ≤ watermark) is skipped by design of a date watermark. The capstone fixes this with
  a content-hash ledger.
- A corrupt `watermark.json` raises rather than silently restarting from scratch.
