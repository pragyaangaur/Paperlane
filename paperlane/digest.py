"""The daily email: one short issue sent as a Kit broadcast.

The email carries no abstracts. It opens with the night's numbers, lists every paper whose
Lean project was built, then papers with code, then every field with its count and a link
into the issue. It is written in Markdown and sent as HTML. Kit's default template wraps
it, adds the unsubscribe link and sends it to every subscriber.
"""

import json
import re
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.request
from datetime import date

from . import USER_AGENT, categories, leancheck

API = "https://api.kit.com/v4/broadcasts"
MAX_CODE = 6
GREEK = {n: c for n, c in zip(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta kappa lambda mu nu xi pi rho sigma tau phi varphi chi psi omega "
    "Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split(),
    "αβγδεεζηθκλμνξπρστφφχψωΓΔΘΛΞΠΣΦΨΩ")}
SYMBOLS = {"le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "neq": "≠", "ne": "≠", "equiv": "≡", "approx": "≈", "sim": "∼",
           "times": "×", "cdot": "·", "pm": "±", "infty": "∞", "to": "→", "in": "∈", "subset": "⊂", "subseteq": "⊆",
           "ldots": "…", "cdots": "⋯", "dots": "…", "mid": "|", "partial": "∂", "nabla": "∇", "ell": "ℓ", "pmod": "mod"}
BLACKBOARD = {c: chr(0x1D538 + i) for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
BLACKBOARD.update({"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"})


def plain(text):
    """TeX in a title, made readable in an email that cannot typeset it."""
    text = re.sub(r"\\mathbb\{?([A-Z])\}?", lambda m: BLACKBOARD[m.group(1)], text or "")
    text = re.sub(r"\\(?:mathcal|mathrm|mathfrak|mathbf|operatorname|text|textit|textbf|emph)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1)) or SYMBOLS.get(m.group(1)) or m.group(1), text)
    text = text.replace("$", "").replace("{", "").replace("}", "").replace("~", " ")
    text = re.sub(r"(?<=\w) ?--- ?(?=\w)", ", ", text)
    text = re.sub(r"(?<=\w)--(?=\w)", "–", text)
    return re.sub(r"\s+", " ", text).strip()


def md_link(text, url):
    return "[" + re.sub(r"([\[\]\\*_])", r"\\\1", text) + f"]({url})"


def authors(names, limit=3):
    if not names:
        return "Unknown authors"
    return ", ".join(names[:limit]) + (" and others" if len(names) > limit else "")


def is_new(p):
    return not p.get("announce_type", "new").startswith("replace")


def paper_link(p, base):
    pid = p["id"].replace("/", "-")
    return f"{base}/p/{pid}.html"


def markdown(day, number, base):
    """(subject, body) for one issue."""
    from . import render  # render imports this module, so import late

    papers = day["papers"]
    fresh = [p for p in papers if is_new(p)]
    updated = len(papers) - len(fresh)
    issue = f"{base}/days/{day['date']}.html"
    d = date.fromisoformat(day["date"])
    lean = [p for p in papers if (p.get("signals") or {}).get("lean_repo")]
    lean.sort(key=lambda p: (not is_new(p), p["id"]))
    code = [p for p in fresh if (p.get("signals") or {}).get("code_links") and p not in lean]

    subject = f"{len(fresh)} new maths papers" + (f", {len(lean)} with Lean" if lean else "") + f" · {d:%a} {d.day} {d:%b}"
    out = [
        f"**{len(fresh)} new maths papers came out last night**"
        + (f", plus {updated} updated versions of older papers." if updated else "."),
        f"{md_link(f'Open issue no. {number}', issue)} to search them or browse by field.",
    ]

    if lean:
        out += ["", "## Proofs you can build", "",
                "These papers link a Lean project. Paperlane builds each one with `lake build` on a clean machine."]
        for p in lean:
            b = leancheck.build_of(p)
            repo = next(g["repo"] for g in p["signals"]["github"] if g.get("lean"))
            result = f"Lean {leancheck.label(b)}" if b else "Lean build check pending"
            tag = "" if is_new(p) else f" (v{p.get('version')})"
            out += ["", f"**{md_link(plain(p['title']), paper_link(p, base))}**{tag}  ",
                    f"{authors(p['authors'])}. {result}. {md_link(repo, 'https://github.com/' + repo)}"]

    if code:
        out += ["", "## With code", ""]
        for p in code[:MAX_CODE]:
            out.append(f"- {md_link(plain(p['title']), paper_link(p, base))}. {authors(p['authors'], 2)}")
        if len(code) > MAX_CODE:
            out += ["", md_link(f"{len(code) - MAX_CODE} more papers link code", issue + "?code=1")]

    fields = render.field_counts(day)
    out += ["", "## By field", "",
            " · ".join(f"{md_link(categories.name(c), f'{issue}?cat={c}')} {n}" for c, n in fields)]

    out += ["", "## Ask your AI", "",
            "Paste this into the assistant you already use and it will explain last night's papers in plain words.", "",
            "> " + render.CURIOUS_PROMPT.format(base=base), "",
            md_link("More prompts", f"{base}/ask.html")]

    out += ["", "---", "",
            f"Paperlane is a free daily list of new arXiv mathematics papers. {render.ARXIV_THANKS}"]
    return subject, "\n".join(out) + "\n"


def send(subject, body, key, day, send_now=False):
    """Create a Kit broadcast for every subscriber. Without send_now it stays a draft in Kit."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "subject": subject,
        "content": to_html(body),
        "description": f"Paperlane {day}",
        "preview_text": body.split("\n", 1)[0].replace("**", ""),
        "public": False,
        "published_at": now.isoformat(),
        # Kit sends a broadcast at send_at and keeps it a draft when send_at is null.
        "send_at": (now + timedelta(minutes=2)).isoformat() if send_now else None,
    }
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST", headers={
        "X-Kit-Api-Key": key, "Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status = json.load(r).get("broadcast", {}).get("status")
            print(f"Kit accepted the broadcast ({r.status}, {status}, {'sending' if send_now else 'draft'}): {subject}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Kit refused the broadcast ({e.code}): {e.read().decode(errors='replace')[:500]}")


def to_html(body):
    """The Markdown this module writes, as HTML, for Kit and for the sign-up page's sample."""
    import html

    def link(m):
        text = re.sub(r"\\(.)", r"\1", m.group(1))
        return f'<a href="{html.escape(m.group(2))}">{text}</a>'

    def inline(t):
        t = html.escape(t, quote=False)
        t = re.sub(r"\[((?:\\.|[^\]\\])*)\]\(([^)\s]+)\)", link, t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)

    out, items = [], []
    for line in body.split("\n"):
        if line.startswith("- "):
            items.append(f"<li>{inline(line[2:])}</li>")
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if line.startswith("## "):
            out.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line == "---":
            out.append("<hr>")
        elif line.strip():
            br = line.endswith("  ")
            out.append(f"<p>{inline(line.rstrip())}</p>" if not br else f"<p>{inline(line.rstrip())}<br>")
    if items:
        out.append("<ul>" + "".join(items) + "</ul>")
    # A line ending in two spaces joins the next line into the same paragraph.
    return "\n".join(out).replace("<br>\n<p>", "<br>")
