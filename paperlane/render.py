"""Render the stored days as a static site: HTML, Markdown, JSON, RSS and llms.txt."""

import html
import json
import shutil
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from . import categories

ASSETS = Path(__file__).parent / "assets"
SECTIONS = [
    ("new", "New papers"),
    ("cross", "Cross-lists from other fields"),
    ("replace", "New versions"),
]
KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"
ARXIV_THANKS = "Thank you to arXiv for use of its open access interoperability."

esc = html.escape


def section_of(p):
    t = p.get("announce_type", "new")
    return "replace" if t.startswith("replace") else ("cross" if t == "cross" else "new")


def anchor(p):
    return p["id"].replace("/", "-")


def long_date(d):
    d = date.fromisoformat(d)
    return f"{d:%A} {d.day} {d:%B %Y}"


def lead_cat(p):
    cats = p.get("math_categories") or []
    return cats[0] if cats else p.get("primary_category") or ""


def sort_key(p):
    return (categories.name(lead_cat(p)), p["id"])


def grouped(day):
    groups = {k: [] for k, _ in SECTIONS}
    for p in day["papers"]:
        groups[section_of(p)].append(p)
    return {k: sorted(v, key=sort_key) for k, v in groups.items()}


def paper_url(base, day, p):
    return f"{base}/p/{anchor(p)}.html"


def paper_md_url(base, p):
    return f"{base}/p/{anchor(p)}.md"


def short_link(url):
    return url.split("://", 1)[-1].rstrip("/")


def counts_line(day):
    g = grouped(day)
    return f"{len(g['new'])} new papers, {len(g['cross'])} cross-lists and {len(g['replace'])} new versions"


# Markdown, for agents first


def signal_notes(p):
    s = p.get("signals") or {}
    notes = []
    checks = {c["repo"]: c for c in s.get("github", [])}
    for url in s.get("code_links", []):
        note = f"code {url}"
        repo = next((r for r in checks if f"github.com/{r}".lower() in url.lower()), None)
        if repo:
            c = checks[repo]
            if c["lean"]:
                note += f" (Lean project: {', '.join(c['lean_paths'])})"
            elif c["status"] == "missing":
                note += " (repository not found)"
            elif c["lean"] is False:
                note += " (no Lean project)"
        notes.append(note)
    if s.get("mentions_lean") and not s.get("lean_repo"):
        notes.append("abstract mentions Lean")
    if s.get("new_version"):
        notes.append(f"new version v{p.get('version')}")
    return notes


def paper_md(p, base, day, full=True):
    cats = ", ".join(c + (" (primary)" if c == p.get("primary_category") else "") for c in p["categories"])
    lines = [f"### {p['title']}", ""]
    lines.append(f"- arXiv: {p['id']} · {p['links']['abs']} · PDF {p['links']['pdf']}")
    lines.append(f"- Authors: {', '.join(p['authors'])}")
    lines.append(f"- Categories: {cats}")
    notes = signal_notes(p)
    if notes:
        lines.append(f"- Signals: {'; '.join(notes)}")
    if p.get("comments"):
        lines.append(f"- Comments: {p['comments']}")
    if p.get("journal_ref"):
        lines.append(f"- Journal reference: {p['journal_ref']}")
    lines.append(f"- Paperlane: {paper_url(base, day, p)} · Markdown {paper_md_url(base, p)}")
    if full:
        lines += ["", p["abstract"]]
    return "\n".join(lines)


def day_md(day, base, built, papers=None, heading=None):
    g = grouped(day)
    out = [
        f"# {heading or 'Paperlane: new arXiv mathematics'}, {long_date(day['date'])}",
        "",
        f"Announced by arXiv on {day['date']}. {counts_line(day)}. Fetched {day['fetched_at']}, built {built}.",
        "",
        "Titles, authors and abstracts come from arXiv. Read the full text on arXiv. Signals are checked by code: "
        "code links found in the abstract or comments, whether a linked GitHub repository contains a Lean project "
        "(a lakefile or lean-toolchain file), and whether the entry is a new version of an older paper. "
        "Paperlane does not rank papers or authors.",
    ]
    if day.get("source") == "api-window":
        out += ["", "This day was backfilled from submission times, so it approximates the announcement and has no new versions."]
    for key, title in SECTIONS:
        items = [p for p in g[key] if papers is None or p in papers]
        if not items:
            continue
        out += ["", f"## {title} ({len(items)})"]
        for p in items:
            out += ["", paper_md(p, base, day)]
    out.append("")
    return "\n".join(out)


def titles_md(day, base, built):
    out = [
        f"# Paperlane titles index, {long_date(day['date'])}",
        "",
        f"One line per paper announced by arXiv on {day['date']} ({counts_line(day)}). Built {built}.",
        f"Abstracts for one subfield are at {base}/latest/<category>.md, for example {base}/latest/math.CO.md, "
        f"the whole day with abstracts is at {base}/latest.md, and one paper is at {base}/p/<id>.md, "
        f"for example {base}/p/{day['papers'][0]['id'].replace('/', '-')}.md (old ids such as math/0601001 use a hyphen).",
        "",
        "Format: arXiv id | categories, primary first | signals | title | authors",
    ]
    g = grouped(day)
    for key, title in SECTIONS:
        if not g[key]:
            continue
        out += ["", f"## {title} ({len(g[key])})", ""]
        for p in g[key]:
            authors = ", ".join(p["authors"][:4]) + (" et al." if len(p["authors"]) > 4 else "")
            cats = " ".join([p["primary_category"]] + [c for c in p["categories"] if c != p["primary_category"]])
            notes = "; ".join(signal_notes(p)) or "-"
            out.append(f"- {p['id']} | {cats} | {notes} | {p['title']} | {authors}")
    out.append("")
    return "\n".join(out)


# HTML


def page(title, body, prefix, built, description=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<link rel="alternate" type="application/rss+xml" title="Paperlane" href="{prefix}feed.xml">
<link rel="alternate" type="text/markdown" title="Today as Markdown" href="{prefix}latest.md">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"></script>
<script defer src="{prefix}assets/app.js"></script>
</head>
<body>
<header class="site">
  <a class="brand" href="{prefix}index.html">Paperlane</a>
  <nav><a href="{prefix}index.html">Today</a><a href="{prefix}archive.html">Archive</a><a href="{prefix}llms.txt">For agents</a><a href="{prefix}feed.xml">RSS</a></nav>
</header>
<main>
{body}
</main>
<footer>
  <p>Titles, authors and abstracts come from arXiv, and every paper links back to arXiv for the full text. Paperlane adds signals that code can check and never scores papers or authors.</p>
  <p>Built {esc(built)}. {ARXIV_THANKS}</p>
</footer>
</body>
</html>
"""


def badges(p):
    s = p.get("signals") or {}
    out = []
    for c in p.get("math_categories") or []:
        cls = "cat primary" if c == categories.ALIASES.get(p["primary_category"], p["primary_category"]) else "cat"
        out.append(f'<span class="{cls}" title="{esc(categories.name(c))}">{esc(c)}</span>')
    if p["primary_category"] and not categories.math_categories([p["primary_category"]]):
        out.append(f'<span class="cat primary other">{esc(p["primary_category"])}</span>')
    checks = {c["repo"].lower(): c for c in s.get("github", [])}
    for url in s.get("code_links", []):
        out.append(f'<a class="sig code" href="{esc(url)}" rel="nofollow">code: {esc(short_link(url))}</a>')
        for repo, c in checks.items():
            if f"github.com/{repo}" in url.lower():
                if c["lean"]:
                    files = ", ".join(c["lean_paths"])
                    out.append(f'<span class="sig lean" title="Found {esc(files)}">Lean project</span>')
                elif c["status"] == "missing":
                    out.append('<span class="sig warn">repo not found</span>')
    if s.get("mentions_lean") and not s.get("lean_repo"):
        out.append('<span class="sig mention">mentions Lean</span>')
    if s.get("new_version"):
        out.append(f'<span class="sig version">v{p.get("version")}</span>')
    if p.get("journal_ref"):
        out.append(f'<span class="sig journal" title="{esc(p["journal_ref"])}">journal ref</span>')
    return " ".join(out)


def paper_html(p, day, prefix="", open_=False):
    s = p.get("signals") or {}
    authors = p["authors"]
    shown = ", ".join(authors[:8]) + (f" and {len(authors) - 8} more" if len(authors) > 8 else "")
    search = " ".join([p["title"], " ".join(authors), p["id"]]).lower()
    extra = []
    if p.get("comments"):
        extra.append(f'<p class="note">Comments: {esc(p["comments"])}</p>')
    if p.get("journal_ref"):
        extra.append(f'<p class="note">Journal reference: {esc(p["journal_ref"])}</p>')
    return f"""<article class="paper" id="{anchor(p)}" data-cats="{' '.join(p.get('math_categories') or [])}"{' data-code="1"' if s.get('code_links') else ''}{' data-lean="1"' if s.get('lean_repo') or s.get('mentions_lean') else ''} data-text="{esc(search)}">
  <h3><a href="{p['links']['abs']}">{esc(p['title'])}</a></h3>
  <p class="authors">{esc(shown)}</p>
  <p class="badges">{badges(p)}</p>
  <details{' open' if open_ else ''}><summary>Abstract</summary>
    <p class="abstract">{esc(p['abstract'])}</p>
    {''.join(extra)}
    <p class="links"><a href="{p['links']['abs']}">arXiv {esc(p['id'])}</a> · <a href="{p['links']['pdf']}">PDF</a> · <a href="{prefix}p/{anchor(p)}.html">Paperlane page</a> · <a href="{prefix}p/{anchor(p)}.md">Markdown</a></p>
  </details>
</article>"""


def filters_html(day):
    counts = {}
    for p in day["papers"]:
        for c in p.get("math_categories") or []:
            counts[c] = counts.get(c, 0) + 1
    chips = [f'<button class="chip" data-cat="" aria-pressed="true">All <span>{len(day["papers"])}</span></button>']
    for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        chips.append(
            f'<button class="chip" data-cat="{c}" aria-pressed="false" title="{esc(c)}">{esc(categories.name(c))} <span>{n}</span></button>'
        )
    code = sum(1 for p in day["papers"] if (p.get("signals") or {}).get("code_links"))
    lean = sum(1 for p in day["papers"] if (p.get("signals") or {}).get("lean_repo") or (p.get("signals") or {}).get("mentions_lean"))
    return f"""<section class="filters" aria-label="Filters">
  <div class="chips">{''.join(chips)}</div>
  <div class="toggles">
    <label><input type="checkbox" id="f-code"> Has code <span>{code}</span></label>
    <label><input type="checkbox" id="f-lean"> Lean <span>{lean}</span></label>
    <input type="search" id="f-q" placeholder="Search titles and authors">
    <span id="f-count" aria-live="polite"></span>
  </div>
</section>"""


def prompt_html(base):
    return f"""<section class="agent" id="agents">
  <h2>Ask your own assistant</h2>
  <p>Paperlane publishes every day as plain Markdown so your assistant can read it. Type your interests and paste the prompt into any assistant that can open web pages.</p>
  <label for="interests">My interests</label>
  <input id="interests" type="text" placeholder="for example extremal graph theory and polyominoes">
  <textarea id="prompt" rows="4" readonly data-base="{esc(base)}"></textarea>
  <button id="copy" type="button">Copy prompt</button>
  <p class="machine">For agents: <a href="llms.txt">llms.txt</a> · <a href="latest-titles.md">titles index</a> · <a href="latest.md">today in Markdown</a> · <a href="latest.json">JSON</a> · <a href="feed.xml">RSS</a></p>
</section>"""


def day_html(day, base, built, prefix, is_index):
    g = grouped(day)
    note = ""
    if day.get("source") == "api-window":
        note = '<p class="warn-note">Backfilled from submission times. It approximates the announcement and has no new versions.</p>'
    files = f"{prefix}days/{day['date']}"
    head = f"""<section class="day">
  <h1>New arXiv mathematics, {long_date(day['date'])}</h1>
  <p class="meta">{counts_line(day)}. Fetched {esc(day['fetched_at'])}. <a href="{files}.md">Markdown</a> · <a href="{files}.json">JSON</a></p>
  {note}
</section>"""
    parts = [head]
    if is_index:
        parts.append(prompt_html(base))
    parts.append(filters_html(day))
    for key, title in SECTIONS:
        if not g[key]:
            continue
        cards = "\n".join(paper_html(p, day, prefix) for p in g[key])
        parts.append(f'<section class="group" data-group="{key}">\n<h2>{title} <span class="n">{len(g[key])}</span></h2>\n{cards}\n</section>')
    title = f"Paperlane: arXiv mathematics, {long_date(day['date'])}"
    return page(title, "\n".join(parts), prefix, built, f"New arXiv mathematics papers announced {day['date']}: {counts_line(day)}.")


def archive_html(days, built):
    rows = []
    for d in days:
        g = grouped(d)
        lean = sum(1 for p in d["papers"] if (p.get("signals") or {}).get("lean_repo"))
        rows.append(
            f'<tr><td><a href="days/{d["date"]}.html">{long_date(d["date"])}</a></td><td>{len(g["new"])}</td>'
            f'<td>{len(g["cross"])}</td><td>{len(g["replace"])}</td><td>{lean}</td>'
            f'<td><a href="days/{d["date"]}.md">md</a> · <a href="days/{d["date"]}.json">json</a></td></tr>'
        )
    body = f"""<section class="day"><h1>Archive</h1><p class="meta">{len(days)} days.</p></section>
<table class="archive"><thead><tr><th>Day</th><th>New</th><th>Cross-lists</th><th>New versions</th><th>Lean repos</th><th>Files</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""
    return page("Paperlane archive", body, "", built)


# Feeds and indexes


def rss(days, base, built_dt, limit_days=1):
    items = []
    for d in days[:limit_days]:
        pub = format_datetime(datetime.fromisoformat(d["fetched_at"].replace("Z", "+00:00")))
        g = grouped(d)
        for p in g["new"] + g["cross"]:
            desc = (
                f"<p>{esc(', '.join(p['authors']))}</p><p>{esc(p['abstract'])}</p>"
                f"<p>{esc('; '.join(signal_notes(p)))}</p>"
                f"<p><a href=\"{p['links']['abs']}\">Read on arXiv</a></p>"
            )
            cats = "".join(f"<category>{esc(c)}</category>" for c in p["categories"])
            items.append(
                f"<item><title>{esc('[' + lead_cat(p) + '] ' + p['title'])}</title>"
                f"<link>{esc(paper_url(base, d, p))}</link>"
                f"<guid isPermaLink=\"false\">arxiv:{esc(p['id'])}v{p['version']}</guid>"
                f"<pubDate>{pub}</pubDate>{cats}<description>{esc(desc)}</description></item>"
            )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>Paperlane: new arXiv mathematics</title>
<link>{esc(base)}/</link>
<atom:link href="{esc(base)}/feed.xml" rel="self" type="application/rss+xml"/>
<description>New arXiv mathematics papers each day, with code and Lean signals. {ARXIV_THANKS}</description>
<language>en</language>
<lastBuildDate>{format_datetime(built_dt)}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""


PROMPT = (
    "Read {base}/latest-titles.md, Paperlane's index of today's new arXiv mathematics papers. "
    "My interests are {interests}. Pick the candidates that fit, read their abstracts in {base}/latest.md "
    "or on arXiv, and tell me which three papers I should read and why."
)


def llms_txt(days, base, built):
    latest = days[0]
    recent = "\n".join(f"- [{d['date']}]({base}/days/{d['date']}.md): {counts_line(d)}" for d in days[:30])
    cats = sorted({c for p in latest["papers"] for c in p.get("math_categories") or []})
    sub = "\n".join(f"- [{categories.name(c)}]({base}/latest/{c}.md): {c}" for c in cats)
    return f"""# Paperlane

> A free daily feed of new arXiv mathematics papers, built for people and their AI agents. Titles, authors, abstracts and categories come from arXiv, and every entry links back to arXiv for the full text. Paperlane adds signals that plain code can check (code links, whether a linked GitHub repository contains a Lean project, and whether an entry is a new version) and never ranks papers or authors. Rank them yourself against your user's interests.

The latest announcement is {latest['date']} ({counts_line(latest)}). Built {built}. arXiv announces new papers at 20:00 US Eastern time from Sunday to Thursday, and Paperlane rebuilds at 02:00 UTC.

## Today

- [Titles index]({base}/latest-titles.md): one line per paper with id, categories, signals, title and authors. Start here.
- [Today in Markdown]({base}/latest.md): every paper with its abstract.
- [Today as JSON]({base}/latest.json): the same data with every field.
- One paper: {base}/p/<id>.md in Markdown or {base}/p/<id>.html for people, for example {base}/p/{anchor(latest['papers'][0])}.md. Old ids such as math/0601001 use a hyphen.
- [RSS]({base}/feed.xml): new papers and cross-lists from the latest announcement.

## Today by subfield

{sub}

## Suggested prompt

{PROMPT.format(base=base, interests="X and Y")}

## Recent days

{recent}
"""


def single_md(p, base, day, built):
    return "\n".join([
        f"# {p['title']}",
        "",
        f"Announced by arXiv on {day['date']} and listed by Paperlane. Built {built}. "
        "The full text is on arXiv, and the signals below are checked by code.",
        "",
        paper_md(p, base, day, full=False).split("\n", 2)[2],
        f"- Day listing: {base}/days/{day['date']}.md",
        "",
        "## Abstract",
        "",
        p["abstract"],
        "",
    ])


def single_html(p, day, base, built):
    body = f"""<section class="day">
  <p class="meta">Announced by arXiv on <a href="../days/{day['date']}.html#{anchor(p)}">{long_date(day['date'])}</a>. <a href="{anchor(p)}.md">Markdown</a></p>
</section>
{paper_html(p, day, "../", open_=True)}"""
    desc = p["abstract"][:200]
    return page(f"{p['title']} | Paperlane", body, "../", built, desc)


def json_day(day, base):
    out = dict(day)
    out["papers"] = [dict(p, paperlane_url=paper_url(base, day, p)) for p in day["papers"]]
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def build(days, out, base, built_dt=None):
    """Write the whole site for `days` (newest first) into `out`."""
    built_dt = built_dt or datetime.now(timezone.utc).replace(microsecond=0)
    built = built_dt.strftime("%Y-%m-%d %H:%M UTC")
    base = base.rstrip("/")
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "days").mkdir(parents=True)
    (out / "p").mkdir()
    (out / "latest").mkdir()
    shutil.copytree(ASSETS, out / "assets")
    (out / ".nojekyll").write_text("")

    # Oldest first, so a paper listed again as a new version keeps its newest entry.
    for d in reversed(days):
        for p in d["papers"]:
            (out / "p" / f"{anchor(p)}.md").write_text(single_md(p, base, d, built))
            (out / "p" / f"{anchor(p)}.html").write_text(single_html(p, d, base, built))
    for d in days:
        (out / "days" / f"{d['date']}.html").write_text(day_html(d, base, built, "../", False))
        (out / "days" / f"{d['date']}.md").write_text(day_md(d, base, built))
        (out / "days" / f"{d['date']}.json").write_text(json_day(d, base))

    latest = days[0]
    (out / "index.html").write_text(day_html(latest, base, built, "", True))
    (out / "latest.md").write_text(day_md(latest, base, built))
    (out / "latest.json").write_text(json_day(latest, base))
    (out / "latest-titles.md").write_text(titles_md(latest, base, built))
    for c in sorted({c for p in latest["papers"] for c in p.get("math_categories") or []}):
        sel = [p for p in latest["papers"] if c in (p.get("math_categories") or [])]
        (out / "latest" / f"{c}.md").write_text(day_md(latest, base, built, sel, f"Paperlane: {categories.name(c)} ({c})"))
    (out / "archive.html").write_text(archive_html(days, built))
    (out / "feed.xml").write_text(rss(days, base, built_dt))
    (out / "llms.txt").write_text(llms_txt(days, base, built))
    print(f"Built {len(days)} days into {out}")
