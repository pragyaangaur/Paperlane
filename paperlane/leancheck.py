"""Does a paper's Lean project build? Checked by running `lake build` on a clean machine.

`plan` picks the repositories to check, `run` clones one and builds it (in a workflow job
with no write access, because the build runs the authors' code), and `record` validates
the results and stores them in data/lean.json. `annotate` adds them to the stored days
before rendering. A build that passes but reports `sorry` is never called a full pass.
"""

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATUSES = ("builds", "sorry", "fails", "timeout", "error")
REPO_RE = re.compile(r"^(?!\.{1,2}/)[A-Za-z0-9_.-]{1,100}/(?!\.{1,2}$)[A-Za-z0-9_.-]{1,100}$")
PATH_RE = re.compile(r"^(?:[A-Za-z0-9_.-]{1,100}/){0,8}[A-Za-z0-9_.-]{0,100}$")
# Older Lean quotes it as 'sorry' and newer Lean as `sorry`.
SORRY_RE = re.compile(r"declaration uses ['`]sorry['`]")
# A repository that was checked once is checked again only when a new version of a paper links it.
RECHECK_AFTER = timedelta(days=7)
MAX_PER_RUN = 20
# A check that could not run (a download failed, or the machine crashed) is tried this many times in all.
MAX_TRIES = 3


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def project_dir(lean_paths):
    """The shallowest folder with a lean-toolchain file, or '' for the repository root."""
    dirs = sorted({p.rsplit("/", 1)[0] if "/" in p else "" for p in lean_paths if p.rsplit("/", 1)[-1] == "lean-toolchain"},
                  key=lambda d: (d.count("/") if d else -1, d))
    if dirs:
        return dirs[0]
    dirs = sorted({p.rsplit("/", 1)[0] if "/" in p else "" for p in lean_paths}, key=lambda d: (d.count("/") if d else -1, d))
    return dirs[0] if dirs else ""


def load(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else {}


def plan(days, results, when=None, force=()):
    """Repositories from these days that have no recent build result, oldest paper first."""
    when = when or now()
    jobs = {}
    for day in days:
        for p in day["papers"]:
            for g in (p.get("signals") or {}).get("github", []):
                repo = g["repo"]
                if not g.get("lean") or repo in jobs:
                    continue
                old = results.get(repo)
                due = old is None or repo in force or (old["status"] == "error" and old.get("tries", 1) < MAX_TRIES)
                if old and not due and (p.get("signals") or {}).get("new_version"):
                    due = when - datetime.fromisoformat(old["checked_at"].replace("Z", "+00:00")) > RECHECK_AFTER
                if due:
                    jobs[repo] = {"repo": repo, "path": project_dir(g.get("lean_paths") or [])}
    return list(jobs.values())[:MAX_PER_RUN]


def sh_retry(cmd, tries=3, wait=30, **kw):
    """sh() again after a pause when a download fails, since Lean's servers sometimes refuse a connection."""
    for i in range(tries):
        code = sh(cmd, **kw)
        if code == 0 or i == tries - 1:
            return code
        time.sleep(wait * (i + 1))


def sh(cmd, cwd=None, timeout=None, log=None):
    """Run a command, appending its output to `log`. Returns the exit code, or None on timeout."""
    with open(log, "a") if log else open(os.devnull, "w") as out:
        out.write(f"\n$ {' '.join(cmd)}\n")
        out.flush()
        try:
            return subprocess.run(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return None


def run(repo, path, out, build_minutes=60, url=None):
    """Clone `repo`, build the Lean project in `path` and write the result to `out`/result.json."""
    if not REPO_RE.match(repo) or not PATH_RE.match(path) or ".." in path.split("/"):
        raise SystemExit(f"Refusing an odd repository or path: {repo} {path}")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "build.log"
    src = out / "src"
    shutil.rmtree(src, ignore_errors=True)
    result = {"repo": repo, "path": path, "commit": None, "toolchain": None, "status": "error",
              "sorries": 0, "seconds": 0, "detail": "", "checked_at": iso(now())}
    start = time.time()

    def finish(status, detail=""):
        result.update(status=status, detail=detail, seconds=int(time.time() - start))
        (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
        print(f"{repo}: {status} {detail}")
        return result

    if sh_retry(["git", "clone", "--depth", "1", "--quiet", url or f"https://github.com/{repo}.git", str(src)], timeout=600, log=log) != 0:
        return finish("error", "the repository could not be cloned")
    result["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()
    proj = src / path if path else src
    tc = proj / "lean-toolchain"
    if not tc.is_file():
        return finish("error", f"no lean-toolchain in {path or 'the root'}")
    result["toolchain"] = tc.read_text().strip()[:100]
    # Fetching Lean itself counts as setup, so a slow download is not blamed on the paper.
    if sh_retry(["elan", "toolchain", "install", result["toolchain"]], timeout=1200, log=log) != 0:
        return finish("error", "the Lean toolchain could not be installed")
    manifest = proj / "lake-manifest.json"
    if manifest.is_file() and '"mathlib"' in manifest.read_text():
        # Downloads Mathlib's compiled files. Without them a build takes hours.
        sh(["lake", "exe", "cache", "get"], cwd=proj, timeout=1800, log=log)
    mark = log.stat().st_size
    code = sh(["lake", "build"], cwd=proj, timeout=build_minutes * 60, log=log)
    with open(log, errors="replace") as f:
        f.seek(mark)
        text = f.read()
    result["sorries"] = len(SORRY_RE.findall(text))
    if code is None:
        return finish("timeout", f"lake build ran for more than {build_minutes} minutes")
    if code != 0:
        return finish("fails", f"lake build exited with code {code}")
    return finish("sorry" if result["sorries"] else "builds")


def clean(r):
    """Keep only well-formed fields from a result written by an untrusted build job."""
    if not isinstance(r, dict) or not REPO_RE.match(str(r.get("repo", ""))) or r.get("status") not in STATUSES:
        return None
    commit = str(r.get("commit") or "")
    return {
        "repo": r["repo"],
        "path": str(r.get("path") or "")[:200] if PATH_RE.match(str(r.get("path") or "")) else "",
        "commit": commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None,
        "toolchain": re.sub(r"[^\w./:+-]", "", str(r.get("toolchain") or ""))[:100] or None,
        "status": r["status"],
        "sorries": max(0, min(int(r.get("sorries") or 0), 100000)),
        "seconds": max(0, min(int(r.get("seconds") or 0), 100000)),
        "detail": re.sub(r"[^\w .,:'()-]", "", str(r.get("detail") or ""))[:200],
        "checked_at": iso(now()),
    }


def record(folder, store, run_url=None, expect=None):
    """Merge every result.json under `folder` into the store file. Returns how many changed.

    `expect` is the set of repositories that were planned. A build job runs untrusted code,
    so a result naming any other repository is dropped.
    """
    results = load(store)
    n, seen = 0, set()
    for f in sorted(Path(folder).glob("**/result.json")):
        try:
            r = clean(json.loads(f.read_text()))
        except (ValueError, TypeError):
            r = None
        if not r or (expect is not None and r["repo"] not in expect):
            print(f"Skipping a malformed or unplanned result in {f}")
            continue
        if run_url:
            r["run"] = run_url
        if r["status"] == "error":
            r["tries"] = previous_tries(results, r["repo"]) + 1
        results[r["repo"]] = r
        seen.add(r["repo"])
        n += 1
    # A build job that died (out of memory or disk) leaves no result. Record that, so the
    # repository is not planned again and the page keeps the plain Lean tag.
    for repo in sorted((expect or set()) - seen):
        results[repo] = {"repo": repo, "path": "", "commit": None, "toolchain": None, "status": "error", "sorries": 0,
                         "seconds": 0, "detail": "the build machine stopped before the build finished",
                         "checked_at": iso(now()), "tries": previous_tries(results, repo) + 1,
                         **({"run": run_url} if run_url else {})}
        n += 1
    Path(store).write_text(json.dumps(dict(sorted(results.items())), indent=1) + "\n")
    return n


def previous_tries(results, repo):
    old = results.get(repo)
    return old.get("tries", 1) if old and old["status"] == "error" else 0


def annotate(days, results):
    """Copy each repository's build result into the papers that link it."""
    for day in days:
        for p in day["papers"]:
            for g in (p.get("signals") or {}).get("github", []):
                if g.get("lean") and g["repo"] in results:
                    g["build"] = results[g["repo"]]
    return days


def build_of(p):
    """The most useful build result among a paper's Lean repositories, or None."""
    found = [g["build"] for g in (p.get("signals") or {}).get("github", []) if g.get("build")]
    order = {s: i for i, s in enumerate(STATUSES)}
    return min(found, key=lambda b: order[b["status"]]) if found else None


def label(b, short=False):
    if b["status"] == "builds":
        return "builds" if short else "builds, no sorry"
    if b["status"] == "sorry":
        n = b["sorries"]
        return f"{n} sorry" if short else f"builds with {n} sorry warning{'s' if n != 1 else ''}"
    if b["status"] == "fails":
        return "fails" if short else "does not build"
    if b["status"] == "timeout":
        return "timed out" if short else "did not finish building within the time limit"
    return "unchecked" if short else "could not be checked"
