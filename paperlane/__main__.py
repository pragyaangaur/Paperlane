"""Command line: `python -m paperlane fetch` and `python -m paperlane build`."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import arxiv, render, signals


def load_days(data):
    files = sorted(Path(data).glob("*.json"), reverse=True)
    return [json.loads(f.read_text()) for f in files]


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def cmd_fetch(args):
    day = arxiv.fetch_api_day(args.api_date) if args.api_date else arxiv.fetch_rss_day()
    if day is None:
        print("No announcement tonight. Leaving the previous day up.")
        set_output("changed", "false")
        return
    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    path = data / f"{day['date']}.json"
    if path.exists() and not args.force:
        old = json.loads(path.read_text())
        if [p["id"] for p in old["papers"]] == [p["id"] for p in day["papers"]]:
            print(f"{day['date']} is already stored with the same papers.")
            set_output("changed", "false")
            return
    day["fetched_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    signals.add_signals(day, check_github=not args.no_github)
    day = {"schema": 1, **day}
    path.write_text(json.dumps(day, ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote {path} with {len(day['papers'])} papers")
    set_output("changed", "true")
    set_output("date", day["date"])


def cmd_build(args):
    days = load_days(args.data)
    if not days:
        sys.exit(f"No days in {args.data}. Run `python -m paperlane fetch` first.")
    render.build(days, args.out, args.base_url)


def main():
    ap = argparse.ArgumentParser(prog="paperlane")
    ap.add_argument("--data", default="data/days", help="folder of stored days (default data/days)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch tonight's announcement and store it")
    f.add_argument("--api-date", help="backfill YYYY-MM-DD from the API by submission time instead of RSS")
    f.add_argument("--no-github", action="store_true", help="skip the Lean checks on GitHub repositories")
    f.add_argument("--force", action="store_true", help="rewrite the day even if it is already stored")
    b = sub.add_parser("build", help="render the site from stored days")
    b.add_argument("--out", default="_site")
    b.add_argument("--base-url", default=os.environ.get("PAPERLANE_BASE_URL", "http://localhost:8000"))
    args = ap.parse_args()
    {"fetch": cmd_fetch, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    main()
