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
# A project with a new commit on its default branch is built again, at most this many per run,
# and not within a day of its last check, so the history follows the project as it changes.
UPDATES_PER_RUN = 6
UPDATE_AFTER = timedelta(days=1)
DECL_KINDS = ("theorems", "definitions", "types", "axioms")
HISTORY_FIELDS = ("checked_at", "commit", "status", "sorries", "theorems", "declarations", "axiom_count",
                  "build_seconds", "lean_files", "lean_lines", "toolchain", "mathlib")
# The first build of each project stops at FIRST_MINUTES so the daily email is not held up.
# A project that runs out of time gets one longer build in a separate run, if it is new.
FIRST_MINUTES = 90
LONG_MINUTES = 300
LONG_WITHIN = timedelta(days=2)
# Files in which authors list the results their formalisation assumes without proving them.
ASSUMPTION_RE = re.compile(r"(?i)^(assumptions?|external[_-]?inputs?|axioms?|hypotheses)(\.(md|json|txt|lean|toml|ya?ml))?$")
MAX_ASSUMPTION_FILES = 5
# Folders that keep old copies of a project, whose assumption files are no longer current.
OLD_DIRS = {"history", "archive", "archived", "old", "deprecated", "legacy"}


def current_assumptions(paths):
    """Assumption files outside folders of old copies."""
    return [p for p in paths if not any(part.lower() in OLD_DIRS for part in p.split("/")[:-1])]
# Axioms every Lean proof may use. Anything else that a project's theorems depend on is reported.
STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
# sorryAx is counted as sorry warnings, so it is not listed again as an axiom.
IGNORED_AXIOMS = STANDARD_AXIOMS | {"sorryAx"}
AXIOM_MINUTES = 20
MAX_AXIOMS = 50
MAX_MODULES = 3000
MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*(\.[A-Za-z_][A-Za-z0-9_']*)*$")
AXIOM_NAME_RE = re.compile(r"^[A-Za-z_][\w.'-]{0,200}$")


def project_modules(proj):
    """Module names of the project's own compiled files, from .lake/build/lib."""
    mods = set()
    for lib in (proj / ".lake" / "build" / "lib" / "lean", proj / ".lake" / "build" / "lib"):
        if not lib.is_dir():
            continue
        for f in lib.rglob("*.olean"):
            name = ".".join(f.relative_to(lib).with_suffix("").parts)
            if MODULE_RE.match(name):
                mods.add(name)
        if mods:
            break
    return sorted(mods)[:MAX_MODULES]


def axiom_script(modules):
    """A Lean file that imports the project and prints every axiom its theorems rest on.

    It walks the constants used by each theorem declared in the project's own modules, with
    one shared visited set, which is what #print axioms does for one theorem at a time.
    """
    imports = "\n".join(f"import {m}" for m in modules)
    mods = ", ".join(f"`{m}" for m in modules)
    return f"""import Lean
{imports}
open Lean Elab Command in
#eval show CommandElabM Unit from do
  let env ← getEnv
  let mine : NameSet := ([{mods}] : List Name).foldl (fun s n => s.insert n) {{}}
  let names := env.header.moduleNames
  let mut stack : Array Name := #[]
  let mut thms := 0
  let mut dThm := 0
  let mut dDef := 0
  let mut dType := 0
  let mut dAx := 0
  for (n, ci) in env.constants.toList do
    if let some idx := env.getModuleIdxFor? n then
      if let some m := names[idx.toNat]? then
        if mine.contains m then
          if let .thmInfo _ := ci then
            stack := stack.push n
            thms := thms + 1
          -- Declarations the authors wrote, without the ones Lean generates.
          -- Only names with their own place in a source file count, which leaves out what Lean generates.
          if !n.isInternal && !isAuxRecursor env n && !isNoConfusion env n && (declRangeExt.find? env n).isSome then
            match ci with
            | .thmInfo _ => dThm := dThm + 1
            | .defnInfo _ => dDef := dDef + 1
            | .opaqueInfo _ => dDef := dDef + 1
            | .inductInfo _ => dType := dType + 1
            | .axiomInfo _ => dAx := dAx + 1
            | _ => pure ()
  let mut seen : NameSet := {{}}
  let mut axs : NameSet := {{}}
  while true do
    match stack.back? with
    | none => break
    | some n =>
      stack := stack.pop
      if seen.contains n then continue
      seen := seen.insert n
      match env.find? n with
      | some (.axiomInfo _) => axs := axs.insert n
      | some ci =>
        let body : Option Expr := match ci with
          | .thmInfo v => some v.value
          | .defnInfo v => some v.value
          | .opaqueInfo v => some v.value
          | _ => none
        for m in ci.type.getUsedConstants do stack := stack.push m
        if let some e := body then
          for m in e.getUsedConstants do stack := stack.push m
      | none => pure ()
  IO.println s!"PAPERLANE_THEOREMS {{thms}}"
  IO.println s!"PAPERLANE_DECLS {{dThm}} {{dDef}} {{dType}} {{dAx}}"
  for a in axs.toList do
    IO.println s!"PAPERLANE_AXIOM {{a}}"
"""


def parse_axioms(text):
    """(theorem count, sorted non-standard axioms) from the script's output, or (None, None)."""
    m = re.search(r"PAPERLANE_THEOREMS (\d+)", text)
    if not m:
        return None, None
    axs = sorted({a for a in re.findall(r"PAPERLANE_AXIOM (\S+)", text) if a not in IGNORED_AXIOMS and AXIOM_NAME_RE.match(a)})
    return int(m.group(1)), axs[:MAX_AXIOMS]


def parse_declarations(text):
    """{"theorems", "definitions", "types", "axioms"} the authors declared, or None."""
    found = re.findall(r"PAPERLANE_DECLS (\d+) (\d+) (\d+) (\d+)", text)
    return dict(zip(DECL_KINDS, map(int, found[-1]))) if found else None


def code_size(proj):
    """(Lean files, lines of Lean) in the project, without its downloaded dependencies."""
    files = lines = 0
    for f in proj.rglob("*.lean"):
        rel = f.relative_to(proj).parts
        if rel[0] in (".lake", "lake-packages") or f.name == ".paperlane_axioms.lean" or f.is_symlink():
            continue
        files += 1
        with open(f, "rb") as fh:
            lines += sum(1 for _ in fh)
    return files, lines


# Why a build failed, in words a reader can act on. A missing lakefile and a Lean error mean
# very different things about a paper's code.
REASONS = {
    "setup": "the project is not set up to build",
    "dependencies": "a dependency could not be downloaded or resolved",
    "lean": "Lean reported errors in the project's own files",
    "other": "lake build failed for another reason",
}
LEAN_ERROR_RE = re.compile(r"\.lean:\d+:\d+: error")


def failure_reason(text):
    """(reason, number of Lean errors) for a failed lake build, from its output."""
    errors = len(LEAN_ERROR_RE.findall(text))
    if re.search(r"(?i)no configuration file|lakefile\.(lean|toml).{0,40}(not found|does not exist)|could not find .{0,20}lakefile", text):
        return "setup", errors
    if re.search(r"(?i)error:.{0,200}(failed to clone|failed to fetch|could not resolve|git exited|cloning|unknown package|manifest|dependency|revision)", text):
        return "dependencies", errors
    if errors:
        return "lean", errors
    return "other", 0


def mathlib_rev(manifest):
    """The Mathlib commit pinned in lake-manifest.json, or None when the project does not use Mathlib."""
    try:
        data = json.loads(Path(manifest).read_text())
    except (OSError, ValueError):
        return None
    for pkg in data.get("packages") or []:
        if isinstance(pkg, dict) and str(pkg.get("name", "")).lower() == "mathlib":
            rev = str(pkg.get("rev") or "")
            return rev if re.fullmatch(r"[0-9a-f]{7,40}", rev) else None
    return None


def check_axioms(proj, log):
    """Runs the axiom script inside the built project. Returns (theorems, axioms, note)."""
    mods = project_modules(proj)
    if not mods:
        return None, None, "no compiled modules were found"
    script = proj / ".paperlane_axioms.lean"
    script.write_text(axiom_script(mods))
    out = Path(log).parent / "axioms.log"
    code = sh(["lake", "env", "lean", script.name], cwd=proj, timeout=AXIOM_MINUTES * 60, log=out)
    text = out.read_text(errors="replace")
    with open(log, "a") as f:
        f.write(text)
    thms, axs = parse_axioms(text)
    if code is None:
        return None, None, f"the axiom check ran for more than {AXIOM_MINUTES} minutes"
    if thms is None:
        return None, None, "the axiom check could not run"
    return thms, axs, ""


def declarations_from(log):
    """The declaration counts the axiom script printed into the build log, if it ran."""
    path = Path(log).parent / "axioms.log"
    return parse_declarations(path.read_text(errors="replace")) if path.is_file() else None


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


# Papers whose authors asked for a build check after the paper was listed, or before Paperlane existed.
# They are stored as one pseudo-day that feeds the Lean planner and the Lean pages, never the issues.
REGISTERED = Path(__file__).resolve().parent.parent / "data" / "registered.json"


def registered(path=REGISTERED):
    """The registered papers as a list with one day, or an empty list."""
    path = Path(path)
    if not path.exists():
        return []
    day = json.loads(path.read_text())
    return [day] if day.get("papers") else []


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


def heads(repos, token=None):
    """The newest commit on each repository's default branch, from the GitHub API."""
    import urllib.error
    import urllib.request
    from . import USER_AGENT
    out = {}
    for repo in sorted(repos):
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.sha"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/HEAD", headers=headers), timeout=30) as r:
                sha = r.read().decode().strip()
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"  could not read the newest commit of {repo}: {e}")
            continue
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            out[repo] = sha
    return out


def plan_updates(results, head, when=None, skip=(), limit=UPDATES_PER_RUN):
    """Checked projects whose default branch has moved on since their last build, longest unchecked first.

    A project that ran out of time is left alone, because each rebuild would take hours.
    """
    when = when or now()
    due = []
    for repo, r in results.items():
        if repo in skip or repo not in head or not r.get("commit") or head[repo] == r["commit"]:
            continue
        if r["status"] == "timeout" or (r["status"] == "error" and r.get("tries", 1) >= MAX_TRIES):
            continue
        checked = datetime.fromisoformat(r["checked_at"].replace("Z", "+00:00"))
        if when - checked >= UPDATE_AFTER:
            due.append((checked, {"repo": repo, "path": r.get("path") or ""}))
    due.sort(key=lambda x: x[0])
    return [j for _, j in due[:limit]]


def plan_long(days, results, when=None, force=()):
    """New results that ran out of time at the first limit, plus any forced repositories."""
    when = when or now()
    paths = {}
    for day in days:
        for p in day["papers"]:
            for g in (p.get("signals") or {}).get("github", []):
                if g.get("lean"):
                    paths.setdefault(g["repo"], project_dir(g.get("lean_paths") or []))
    jobs = []
    for repo, r in sorted(results.items()):
        recent = when - datetime.fromisoformat(r["checked_at"].replace("Z", "+00:00")) <= LONG_WITHIN
        first = r["status"] == "timeout" and (r.get("minutes") or FIRST_MINUTES) < LONG_MINUTES
        if repo in force or (first and recent and not r.get("long_tried")):
            jobs.append({"repo": repo, "path": r.get("path") or paths.get(repo, "")})
    return jobs[:MAX_PER_RUN]


def assumption_files(src):
    """Paths, relative to the repository, of files that list a project's assumed inputs."""
    found = []
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("build", "node_modules") and d.lower() not in OLD_DIRS)
        for name in sorted(files):
            if ASSUMPTION_RE.match(name):
                found.append(os.path.relpath(os.path.join(root, name), src).replace(os.sep, "/"))
    found.sort(key=lambda f: (f.count("/"), f))
    return found[:MAX_ASSUMPTION_FILES]


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
              "sorries": 0, "seconds": 0, "detail": "", "minutes": build_minutes, "assumptions": [], "checked_at": iso(now()),
              # The check always builds the newest commit on the default branch, not a commit the paper names.
              "source": "default branch"}
    start = time.time()

    def finish(status, detail=""):
        result.update(status=status, detail=detail, seconds=int(time.time() - start))
        (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
        print(f"{repo}: {status} {detail}")
        return result

    if sh_retry(["git", "clone", "--depth", "1", "--quiet", url or f"https://github.com/{repo}.git", str(src)], timeout=600, log=log) != 0:
        return finish("error", "the repository could not be cloned")
    result["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()
    result["assumptions"] = assumption_files(src)
    proj = src / path if path else src
    tc = proj / "lean-toolchain"
    if not tc.is_file():
        return finish("error", f"no lean-toolchain in {path or 'the root'}")
    result["toolchain"] = tc.read_text().strip()[:100]
    result["lean_files"], result["lean_lines"] = code_size(proj)
    if not any((proj / f).is_file() for f in ("lakefile.lean", "lakefile.toml")):
        result["reason"] = "setup"
        return finish("fails", f"no lakefile in {path or 'the root'}")
    # Fetching Lean itself counts as setup, so a slow download is not blamed on the paper.
    if sh_retry(["elan", "toolchain", "install", result["toolchain"]], timeout=1200, log=log) != 0:
        return finish("error", "the Lean toolchain could not be installed")
    manifest = proj / "lake-manifest.json"
    result["mathlib"] = mathlib_rev(manifest)
    if manifest.is_file() and '"mathlib"' in manifest.read_text():
        # Downloads Mathlib's compiled files. Without them a build takes hours.
        sh(["lake", "exe", "cache", "get"], cwd=proj, timeout=1800, log=log)
    mark = log.stat().st_size
    began = time.time()
    code = sh(["lake", "build"], cwd=proj, timeout=build_minutes * 60, log=log)
    result["build_seconds"] = int(time.time() - began)
    with open(log, errors="replace") as f:
        f.seek(mark)
        text = f.read()
    result["sorries"] = len(SORRY_RE.findall(text))
    if code is None:
        return finish("timeout", f"lake build ran for more than {build_minutes} minutes")
    if code != 0:
        result["reason"], result["lean_errors"] = failure_reason(text)
        return finish("fails", f"lake build exited with code {code}")
    result["theorems"], result["axioms"], result["axiom_note"] = check_axioms(proj, log)
    result["declarations"] = declarations_from(log)
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
        "minutes": max(0, min(int(r.get("minutes") or FIRST_MINUTES), 360)),
        "assumptions": [a for a in (r.get("assumptions") or []) if isinstance(a, str) and a and PATH_RE.match(a) and ".." not in a][:MAX_ASSUMPTION_FILES],
        "reason": r["reason"] if r.get("reason") in REASONS and r["status"] == "fails" else None,
        "lean_errors": max(0, min(int(r.get("lean_errors") or 0), 100000)) if r["status"] == "fails" else 0,
        "mathlib": r["mathlib"] if isinstance(r.get("mathlib"), str) and re.fullmatch(r"[0-9a-f]{7,40}", r["mathlib"]) else None,
        "source": "default branch",
        "theorems": max(0, min(int(r["theorems"]), 10**7)) if isinstance(r.get("theorems"), int) else None,
        "axioms": sorted({a for a in r["axioms"] if isinstance(a, str) and AXIOM_NAME_RE.match(a) and a not in IGNORED_AXIOMS})[:MAX_AXIOMS] if isinstance(r.get("axioms"), list) else None,
        "axiom_note": re.sub(r"[^\w .,:'()-]", "", str(r.get("axiom_note") or ""))[:200],
        "declarations": clean_declarations(r.get("declarations")),
        "lean_files": bounded(r.get("lean_files"), 10**6),
        "lean_lines": bounded(r.get("lean_lines"), 10**8),
        "build_seconds": bounded(r.get("build_seconds"), 100000),
        "checked_at": iso(now()),
    }


def bounded(v, top):
    return max(0, min(v, top)) if isinstance(v, int) and not isinstance(v, bool) else None


def clean_declarations(d):
    if not isinstance(d, dict):
        return None
    out = {k: bounded(d.get(k), 10**7) for k in DECL_KINDS}
    return out if all(v is not None for v in out.values()) else None


def snapshot(r):
    """One line of a project's history: what a single check found."""
    snap = {k: r.get(k) for k in HISTORY_FIELDS if k != "axiom_count"}
    snap["axiom_count"] = len(r["axioms"]) if isinstance(r.get("axioms"), list) else None
    return snap


def add_history(history_path, results, repos):
    """Append the newest result of each repository in `repos` to the history file."""
    path = Path(history_path)
    hist = json.loads(path.read_text()) if path.exists() else {}
    for repo in sorted(repos):
        if repo in results:
            hist.setdefault(repo, []).append(snapshot(results[repo]))
    path.write_text(json.dumps(dict(sorted(hist.items())), indent=1) + "\n")


def record(folder, store, run_url=None, expect=None, keep_missing=False, history=None):
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
        if keep_missing and r["status"] == "error" and results.get(r["repo"], {}).get("status") == "timeout":
            continue
        if r["status"] == "error":
            r["tries"] = previous_tries(results, r["repo"]) + 1
        results[r["repo"]] = r
        seen.add(r["repo"])
        n += 1
    # A build job that died (out of memory or disk) leaves no result. Record that, so the
    # repository is not planned again and the page keeps the plain Lean tag.
    # The longer second run keeps the first result when its own machine stopped, and marks
    # it as tried so it is not planned again.
    if keep_missing:
        for repo in (expect or set()) - seen:
            if repo in results:
                results[repo]["long_tried"] = True
    for repo in [] if keep_missing else sorted((expect or set()) - seen):
        results[repo] = {"repo": repo, "path": "", "commit": None, "toolchain": None, "status": "error", "sorries": 0,
                         "seconds": 0, "detail": "the build machine stopped before the build finished",
                         "checked_at": iso(now()), "tries": previous_tries(results, repo) + 1,
                         **({"run": run_url} if run_url else {})}
        n += 1
    Path(store).write_text(json.dumps(dict(sorted(results.items())), indent=1) + "\n")
    if history:
        add_history(history, results, seen | (set() if keep_missing else (expect or set()) - seen))
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
        if short:
            return "fails"
        why = REASONS.get(b.get("reason") or "")
        if b.get("reason") == "lean" and b.get("lean_errors"):
            n = b["lean_errors"]
            why = f"Lean reported {n} error{'s' if n != 1 else ''} in the project's own files"
        return f"does not build: {why}" if why else "does not build"
    if b["status"] == "timeout":
        return "too large" if short else "is too large to build within the check's time limit"
    return "unchecked" if short else "could not be checked"
