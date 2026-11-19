"""The code licence of every checked Lean repository, from GitHub's licence detection.

Paperlane does not own the Lean projects it builds. Each one is under its authors' own licence,
so the licence is shown next to the build result for anyone who wants to reuse the code. The
licence is read from the repository's default branch, which can differ from the built commit.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import USER_AGENT

REFRESH_DAYS = 30


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def lookup(repo, token=None):
    """Ask GitHub which licence the repository's default branch has.

    spdx is an SPDX id such as "MIT", "other" when GitHub found a licence file it could not
    name, or null when the repository has no licence file. A repository without a licence
    gives nobody the right to reuse its code.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repo}/license"
    entry = {"checked_at": now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {**entry, "spdx": None, "name": None, "url": None}
        print(f"  licence lookup failed for {repo}: HTTP {e.code}")
        return None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  licence lookup failed for {repo}: {e}")
        return None
    lic = data.get("license") or {}
    spdx = lic.get("spdx_id")
    if not spdx or spdx == "NOASSERTION":
        spdx = "other"
    name = lic.get("name") if spdx != "other" else "a licence GitHub could not identify"
    return {**entry, "spdx": spdx, "name": name, "url": data.get("html_url")}


def refresh(repos, store, token=None, when=None):
    """Look up repositories with no stored licence or one older than REFRESH_DAYS. Returns the count changed."""
    when = when or now()
    known = load(store)
    changed = 0
    for repo in sorted(repos):
        old = known.get(repo)
        if old:
            age = when - datetime.fromisoformat(old["checked_at"].replace("Z", "+00:00"))
            if age < timedelta(days=REFRESH_DAYS):
                continue
        new = lookup(repo, token)
        if new is None:
            continue
        if not old or {k: v for k, v in old.items() if k != "checked_at"} != {k: v for k, v in new.items() if k != "checked_at"}:
            changed += 1
        known[repo] = new
    Path(store).write_text(json.dumps(dict(sorted(known.items())), indent=1) + "\n")
    return changed


def label(entry):
    """Plain words for a stored licence entry."""
    if not entry:
        return "not looked up yet"
    if entry.get("spdx") is None:
        return "no licence file, so the code is not licensed for reuse"
    if entry["spdx"] == "other":
        return "a licence file GitHub could not identify"
    return entry.get("name") or entry["spdx"]
