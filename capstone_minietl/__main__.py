"""CLI: python -m capstone_minietl run CONFIG.json"""
import argparse
import logging
import sys

from capstone_minietl.runner import run
from d2_6_registry.solution import ConfigError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="minietl", description="Run a config-driven ETL pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="run one pipeline config")
    p_run.add_argument("config")
    p_run.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        report = run(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    print(f"status={report['status']} files={len(report['files'])} "
          f"duration={report['duration_seconds']}s report={report['report_path']}")
    for step in report["steps"]:
        print(f"  {step['step']:<14} in={step['rows_in']:<5} out={step['rows_out']:<5} rejected={step['rejected']}")
    if report["quality"]:
        for r in report["quality"]["results"]:
            mark = "ok  " if r["passed"] else ("FAIL" if r["severity"] == "error" else "warn")
            print(f"  [{mark}] {r['name']} failed={r['failed_count']}")
    for err in report["errors"]:
        print(f"  error: {err}", file=sys.stderr)
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
