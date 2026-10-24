"""Checkable signals for each paper, computed by plain code only.

Nothing here uses a language model, so a signal is either read straight from arXiv's
metadata or from a public repository. A bad summary can never create a Lean claim.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import USER_AGENT

CODE_HOSTS = {"github.com", "gitlab.com", "codeberg.org", "bitbucket.org", "git.sr.ht", "huggingface.co"}
LEAN_FILES = {"lean-toolchain", "lakefile.lean", "lakefile.toml"}
GITHUB_NOT_USERS = {"orgs", "topics", "sponsors", "features", "about", "marketplace", "settings", "search"}

URL_RE = re.compile(
    r"https?://[^\s<>\"'{}|\\^`]+"
    r"|(?<![\w/.@-])(?:www\.)?(?:github\.com|gitlab\.com|codeberg\.org|bitbucket\.org)/[^\s<>\"'{}|\\^`]+",
    re.I,
)
# "Lean" is capitalised in every use that names the prover, so this is case-sensitive.
LEAN_RE = re.compile(
    r"\bLean[ ~]?4\b|\bMathlib\b|\b(?:in|using|with|into) Lean\b|\bLean (?:proof|formali[sz]ation|theorem prover|code|project|library)",
)


def _trim(url):
    url = url.rstrip(".,;:!?'\"")
    for open_, close in ("()", "[]", "{}"):
        while url.endswith(close) and url.count(close) > url.count(open_):
            url = url[:-1].rstrip(".,;:!?")
    return url


def find_links(text):
    """Every URL in a piece of text, normalised to https, without duplicates."""
    seen = []
    for m in URL_RE.finditer(text or ""):
        url = _trim(m.group(0))
        if not url.lower().startswith("http"):
            url = "https://" + url
        url = re.sub(r"^http://", "https://", url, flags=re.I)
        if url not in seen:
            seen.append(url)
    return seen


def host(url):
    h = urllib.parse.urlsplit(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def github_repo(url):
    """'owner/repo' for a GitHub repository URL, or None."""
    if host(url) != "github.com":
        return None
    parts = [p for p in urllib.parse.urlsplit(url).path.split("/") if p]
    if len(parts) < 2 or parts[0].lower() in GITHUB_NOT_USERS:
        return None
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return f"{parts[0]}/{repo}"


def lean_check(repo, cache, token=None):
    """Look for a Lean project file anywhere in a GitHub repo's default branch.

    Returns {"repo", "status", "lean", "lean_paths"} where status is "ok", "missing"
    (no such public repo) or "error", and lean is True, False or None when unknown.
    """
    if repo in cache:
        return cache[repo]
    url = f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    result = {"repo": repo, "status": "ok", "lean": None, "lean_paths": []}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            tree = json.load(r)
        paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
        hits = [p for p in paths if p.rsplit("/", 1)[-1] in LEAN_FILES]
        result["lean_paths"] = hits[:5]
        result["lean"] = bool(hits) or (None if tree.get("truncated") else False)
    except urllib.error.HTTPError as e:
        # 404 is a missing or private repo, 409 an empty one.
        result["status"] = "missing" if e.code in (404, 409, 451) else "error"
        if e.code in (409,):
            result["lean"] = False
        if e.code in (403, 429):
            print(f"  GitHub rate limit hit at {repo}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        result["status"] = "error"
        print(f"  GitHub check failed for {repo}: {e}")
    cache[repo] = result
    return result


def compute(paper, cache, check_github=True, token=None):
    text = " ".join(filter(None, [paper.get("abstract"), paper.get("comments")]))
    links = find_links(text)
    code = [u for u in links if host(u) in CODE_HOSTS]
    repos = []
    for u in code:
        r = github_repo(u)
        if r and r not in repos:
            repos.append(r)
    checks = [lean_check(r, cache, token) for r in repos] if check_github else []
    return {
        "code_links": code,
        "other_links": [u for u in links if u not in code],
        "github": checks,
        "lean_repo": any(c["lean"] for c in checks),
        "mentions_lean": bool(LEAN_RE.search(text) or LEAN_RE.search(paper.get("title") or "")),
        "new_version": paper.get("announce_type", "").startswith("replace") or (paper.get("version") or 1) > 1,
        "journal_ref": bool(paper.get("journal_ref")),
    }


def add_signals(day, check_github=True):
    token = os.environ.get("GITHUB_TOKEN")
    cache = {}
    for p in day["papers"]:
        p["signals"] = compute(p, cache, check_github, token)
    if cache:
        found = sum(1 for c in cache.values() if c["lean"])
        print(f"GitHub: checked {len(cache)} repos, {found} Lean projects")
    return day
