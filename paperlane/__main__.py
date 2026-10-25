"""Command line: `python -m paperlane fetch` and `python -m paperlane build`."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import USER_AGENT, arxiv, render, signals


def load_days(data):
    files = sorted(Path(data).glob("*.json"), reverse=True)
    return [json.loads(f.read_text()) for f in files]


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def stored_ids(path):
    return [p["id"] for p in json.loads(path.read_text())["papers"]] if path.exists() else None


def cmd_fetch(args):
    data = Path(args.data)
    if args.api_date:
        day = arxiv.fetch_api_day(args.api_date)
    else:
        # The backup runs read the feed again. When the night is already stored there is
        # no need to ask the arXiv API about every paper a second time.
        when, items = arxiv.read_rss()
        if items and not args.force and stored_ids(data / f"{when}.json") == [i["id"] for i in items]:
            print(f"{when} is already stored with the same papers.")
            set_output("changed", "false")
            return
        day = arxiv.fetch_rss_day((when, items))
    if day is None:
        print("No announcement tonight. Leaving the previous day up.")
        set_output("changed", "false")
        return
    data.mkdir(parents=True, exist_ok=True)
    path = data / f"{day['date']}.json"
    if not args.force and stored_ids(path) == [p["id"] for p in day["papers"]]:
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
    render.build(days, args.out, args.base_url, goatcounter=args.goatcounter)


def live_date(site):
    """The date of the issue the live site is serving, or None when it cannot be read."""
    url = f"{site.rstrip('/')}/latest.json?t={int(time.time())}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as r:
            return json.load(r).get("date")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"Could not read {url}: {e}")
        return None


def cmd_check(args):
    """Compare the newest stored day with the live site.

    Sets `stale=true` when the site is behind the stored data, so a backup run can
    deploy again after a failed deploy. With --final it also fails when a weekday
    ends with no issue for that day, which makes GitHub email the repository owner.
    """
    files = sorted(Path(args.data).glob("*.json"))
    newest = files[-1].stem if files else None
    live = live_date(args.site)
    print(f"Newest stored day {newest}, live site shows {live}")
    set_output("stale", "true" if live != newest else "false")
    if not args.final:
        return
    today = datetime.now(timezone.utc).date()
    problems = []
    if today.weekday() < 5:
        if newest != today.isoformat():
            problems.append(f"No issue was stored for {today}. Every run today failed to fetch it, or arXiv had a holiday.")
        elif live != newest:
            problems.append(f"The issue for {today} is stored but the live site still shows {live}. The deploy failed.")
    elif live != newest:
        problems.append(f"The live site shows {live} but the newest stored day is {newest}. The deploy failed.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not problems:
        print("All good.")
        if summary:
            Path(summary).write_text(f"Paperlane is up to date. The live site shows {live}.\n")
        return
    for msg in problems:
        print(f"::error title=Paperlane missed an issue::{msg}")
    if summary:
        Path(summary).write_text("## Paperlane missed an issue\n\n" + "\n\n".join(problems) +
                                 "\n\nRe-run the Daily feed workflow by hand once arXiv is reachable.\n")
    sys.exit(1)


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
    b.add_argument("--goatcounter", default=os.environ.get("PAPERLANE_GOATCOUNTER"), help="GoatCounter site code for visitor counts")
    c = sub.add_parser("check", help="compare the newest stored day with the live site")
    c.add_argument("--site", required=True, help="the live site's base URL")
    c.add_argument("--final", action="store_true", help="fail when today's issue is missing (the last run of the day)")
    args = ap.parse_args()
    {"fetch": cmd_fetch, "build": cmd_build, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    main()
