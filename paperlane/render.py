"""Render the stored days as a static site: HTML, Markdown, JSON, RSS and llms.txt."""

import html
import json
import shutil
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from . import categories, signals

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

ICON_SEARCH = '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M13 13l4.5 4.5"/></svg>'
ICON_THEME = '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7"/><path d="M10 3a7 7 0 0 0 0 14z" class="fill"/></svg>'

# Runs before the page paints, so a saved theme never flashes the wrong colours.
THEME_BOOT = (
    "<script>try{var t=localStorage.getItem('paperlane-theme');"
    "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}</script>"
)


def page(title, body, prefix, built, description="", base="", wide=False):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="color-scheme" content="light dark">
{THEME_BOOT}
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<link rel="alternate" type="application/rss+xml" title="Paperlane" href="{prefix}feed.xml">
<link rel="alternate" type="text/markdown" title="Today as Markdown" href="{prefix}latest.md">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"></script>
<script defer src="{prefix}assets/app.js"></script>
</head>
<body data-prefix="{prefix}" data-base="{esc(base)}">
<header class="site">
  <div class="bar">
    <a class="brand" href="{prefix}index.html">Paperlane</a>
    <form class="lookup" action="{prefix}paper.html" method="get" role="search">
      {ICON_SEARCH}
      <input name="id" type="search" placeholder="Paste any arXiv link or id" aria-label="Open any arXiv paper by link or id" autocomplete="off" spellcheck="false">
      <button type="submit">Open</button>
    </form>
    <nav>
      <a href="{prefix}index.html">Today</a>
      <a href="{prefix}archive.html">Archive</a>
      <button type="button" class="link" data-open-ask>Ask your AI</button>
      <a href="{prefix}llms.txt" title="Index for AI agents">llms.txt</a>
      <button type="button" class="theme" data-theme-toggle title="Switch theme">{ICON_THEME}<span>Auto</span></button>
    </nav>
  </div>
</header>
<main class="{'wide' if wide else 'narrow'}">
{body}
</main>
{ask_dialog(prefix, base)}
<footer>
  <p>Titles, authors and abstracts come from arXiv, and every paper links back to arXiv for the full text. Paperlane adds signals that code can check and never scores papers or authors.</p>
  <p>Built {esc(built)}. <a href="{prefix}feed.xml">RSS</a> · <a href="{prefix}latest.md">Today in Markdown</a> · <a href="{prefix}latest.json">JSON</a> · <a href="https://github.com/pragyaangaur/Paperlane">Source</a>. {ARXIV_THANKS}</p>
</footer>
</body>
</html>
"""


def ask_dialog(prefix, base):
    return f"""<dialog class="ask" id="ask">
  <form method="dialog" class="close"><button aria-label="Close">×</button></form>
  <h2>Ask your own AI about today</h2>
  <p>Every day is published as plain Markdown that an assistant can read. Write what you work on, copy the prompt, and paste it into any assistant that can open web pages.</p>
  <label for="interests">What are you interested in?</label>
  <input id="interests" type="text" placeholder="for example extremal graph theory and polyominoes">
  <textarea id="prompt" rows="5" readonly data-base="{esc(base)}"></textarea>
  <div class="row"><button id="copy-prompt" type="button" class="primary">Copy prompt</button>
  <span class="machine">Files for agents: <a href="{prefix}latest-titles.md">titles index</a> · <a href="{prefix}latest.md">full day</a> · <a href="{prefix}latest.json">JSON</a> · <a href="{prefix}llms.txt">llms.txt</a></span></div>
</dialog>"""


def badges(p):
    s = p.get("signals") or {}
    out = []
    primary = categories.ALIASES.get(p["primary_category"], p["primary_category"])
    for c in p.get("math_categories") or []:
        cls = "cat primary" if c == primary else "cat"
        out.append(f'<span class="{cls}" title="{esc(categories.name(c))}">{esc(c)}</span>')
    if p["primary_category"] and not categories.math_categories([p["primary_category"]]):
        out.append(f'<span class="cat other" title="Primary category outside mathematics">{esc(p["primary_category"])}</span>')
    checks = {c["repo"].lower(): c for c in s.get("github", [])}
    for url in s.get("code_links", []):
        lean = missing = None
        for repo, c in checks.items():
            if f"github.com/{repo}" in url.lower():
                lean = c["lean"] and ", ".join(c["lean_paths"])
                missing = c["status"] == "missing"
        if lean:
            out.append(f'<a class="sig lean" href="{esc(url)}" rel="nofollow" title="Lean project: found {esc(lean)}">Lean project</a>')
        out.append(f'<a class="sig code" href="{esc(url)}" rel="nofollow" title="{esc(url)}">{"repo not found: " if missing else "code: "}{esc(short_link(url))}</a>')
    if s.get("mentions_lean") and not s.get("lean_repo"):
        out.append('<span class="sig mention" title="The abstract or comments mention Lean, but no Lean repository was found">mentions Lean</span>')
    if s.get("new_version"):
        out.append(f'<span class="sig version" title="A new version of an older paper">v{p.get("version")}</span>')
    if p.get("journal_ref"):
        out.append(f'<span class="sig journal" title="{esc(p["journal_ref"])}">published</span>')
    return "".join(out)


def linkify(text):
    """Escape text and turn the URLs in it into links."""
    out, last = [], 0
    for m in signals.URL_RE.finditer(text):
        url = signals._trim(m.group(0))
        href = url if url.lower().startswith("http") else "https://" + url
        out += [esc(text[last : m.start()]), f'<a href="{esc(href)}" rel="nofollow">{esc(url)}</a>']
        last = m.start() + len(url)
    return "".join(out) + esc(text[last:])


def paper_html(p, day, prefix="", expanded=False):
    s = p.get("signals") or {}
    authors = p["authors"]
    shown = ", ".join(authors[:8]) + (f" and {len(authors) - 8} more" if len(authors) > 8 else "")
    pid = anchor(p)
    notes = []
    if p.get("comments"):
        notes.append(f'<p class="note"><b>Comments</b> {linkify(p["comments"])}</p>')
    if p.get("journal_ref"):
        notes.append(f'<p class="note"><b>Journal</b> {esc(p["journal_ref"])}</p>')
    attrs = [
        f'id="{pid}"',
        f'data-cats="{" ".join(p.get("math_categories") or [])}"',
        f'data-kind="{section_of(p)}"',
    ]
    if s.get("code_links"):
        attrs.append('data-code="1"')
    if s.get("lean_repo") or s.get("mentions_lean"):
        attrs.append('data-lean="1"')
    return f"""<article class="paper{' expanded' if expanded else ''}" {' '.join(attrs)}>
  <div class="top"><a class="aid" href="{p['links']['abs']}" title="Open on arXiv">arXiv:{esc(p['id'])}</a>{badges(p)}</div>
  <h3><a href="{prefix}p/{pid}.html">{esc(p['title'])}</a></h3>
  <p class="authors">{esc(shown)}</p>
  <div class="abstract"><p>{esc(p['abstract'])}</p>{''.join(notes)}</div>
  <div class="actions">
    <button type="button" class="act" data-act="expand" aria-expanded="{'true' if expanded else 'false'}">{'Show less' if expanded else 'Read abstract'}</button>
    <button type="button" class="act" data-act="md" data-md="{prefix}p/{pid}.md" aria-expanded="false">Markdown</button>
    <a class="act" href="{p['links']['pdf']}">PDF</a>
    <a class="act" href="{p['links']['abs']}">arXiv</a>
    <button type="button" class="act" data-act="link" data-url="{prefix}p/{pid}.html">Copy link</button>
  </div>
  <div class="md-panel" hidden></div>
</article>"""


def sidebar_html(day):
    papers = day["papers"]
    sig = [p.get("signals") or {} for p in papers]
    counts = {}
    for p in papers:
        for c in p.get("math_categories") or []:
            counts[c] = counts.get(c, 0) + 1
    g = grouped(day)
    kinds = "".join(
        f'<label class="opt"><input type="checkbox" name="kind" value="{k}" checked> <span>{t}</span><em>{len(g[k])}</em></label>'
        for k, t in [("new", "New papers"), ("cross", "Cross-lists"), ("replace", "New versions")]
        if g[k]
    )
    code = sum(1 for s in sig if s.get("code_links"))
    lean = sum(1 for s in sig if s.get("lean_repo") or s.get("mentions_lean"))
    subs = "".join(
        f'<label class="opt"><input type="checkbox" name="cat" value="{c}"> <span>{esc(categories.name(c))}</span><em>{n}</em></label>'
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    return f"""<aside class="filters" id="filters" aria-label="Filters">
  <div class="filters-head"><h2>Filters</h2><button type="button" class="link" data-clear>Clear all</button><button type="button" class="link close-filters" data-close-filters>Done</button></div>
  <label class="search"><span class="sr">Filter this day</span>{ICON_SEARCH}<input type="search" id="f-q" placeholder="Filter by word, author or id" autocomplete="off"></label>
  <fieldset><legend>Signals</legend>
    <label class="opt"><input type="checkbox" id="f-code"> <span>Has code</span><em>{code}</em></label>
    <label class="opt"><input type="checkbox" id="f-lean"> <span>Lean</span><em>{lean}</em></label>
  </fieldset>
  <fieldset><legend>Show</legend>{kinds}</fieldset>
  <fieldset class="subs"><legend>Subfields <small>pick any number</small></legend>
    <input type="search" id="f-sub" class="mini" placeholder="Find a subfield" autocomplete="off">
    <div class="sub-list">{subs}</div>
  </fieldset>
</aside>"""


def day_html(day, base, built, prefix, is_index):
    g = grouped(day)
    note = ""
    if day.get("source") == "api-window":
        note = '<p class="warn-note">This day was backfilled from submission times. It approximates the announcement and has no new versions.</p>'
    files = f"{prefix}days/{day['date']}"
    sections = []
    for key, title in SECTIONS:
        if not g[key]:
            continue
        cards = "\n".join(paper_html(p, day, prefix) for p in g[key])
        sections.append(f'<section class="group" data-group="{key}">\n<h2>{title} <span class="n">{len(g[key])}</span></h2>\n{cards}\n</section>')
    body = f"""<div class="layout">
{sidebar_html(day)}
<div class="content">
  <section class="day">
    <p class="eyebrow">{'Latest announcement' if is_index else 'Archived day'}</p>
    <h1>New arXiv mathematics, {long_date(day['date'])}</h1>
    <p class="meta">{counts_line(day)}. Fetched {esc(day['fetched_at'].replace('T', ' ').replace('Z', ' UTC'))}. Whole day as <a href="{files}.md">Markdown</a> or <a href="{files}.json">JSON</a>.</p>
    {note}
  </section>
  <div class="results">
    <button type="button" class="open-filters" data-open-filters>Filters <span id="f-badge"></span></button>
    <span id="f-count" aria-live="polite"></span>
    <span id="f-pills"></span>
  </div>
  <p class="empty" id="f-empty" hidden>No papers match these filters. <button type="button" class="link" data-clear>Clear all filters</button></p>
  <p class="lookup-hint" id="f-lookup" hidden></p>
  {''.join(sections)}
</div>
</div>"""
    title = f"Paperlane: arXiv mathematics, {long_date(day['date'])}"
    return page(title, body, prefix, built, f"New arXiv mathematics papers announced {day['date']}: {counts_line(day)}.", base, wide=True)


def archive_html(days, built, base):
    rows = []
    for d in days:
        g = grouped(d)
        lean = sum(1 for p in d["papers"] if (p.get("signals") or {}).get("lean_repo"))
        rows.append(
            f'<tr><td><a href="days/{d["date"]}.html">{long_date(d["date"])}</a></td><td>{len(g["new"])}</td>'
            f'<td>{len(g["cross"])}</td><td>{len(g["replace"])}</td><td>{lean}</td>'
            f'<td><a href="days/{d["date"]}.md">md</a> · <a href="days/{d["date"]}.json">json</a></td></tr>'
        )
    body = f"""<section class="day"><p class="eyebrow">Every day so far</p><h1>Archive</h1><p class="meta">{len(days)} days. Any paper listed on these days opens from the search box at the top.</p></section>
<div class="table-wrap"><table class="archive"><thead><tr><th>Day</th><th>New</th><th>Cross-lists</th><th>New versions</th><th>Lean repos</th><th>Files</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>"""
    return page("Paperlane archive", body, "", built, "Every day of new arXiv mathematics on Paperlane.", base)


def lookup_html(built, base):
    body = """<section class="day"><p class="eyebrow">Open a paper</p><h1 id="lk-title">Open any arXiv paper</h1>
<p class="meta" id="lk-status">Paste an arXiv link or id into the box at the top, for example 2610.30655 or https://arxiv.org/abs/2610.30655.</p></section>
<div id="lk-result"></div>"""
    return page("Open an arXiv paper | Paperlane", body, "", built, "Open any arXiv paper on Paperlane by its link or id.", base)


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

The latest announcement is {latest['date']} ({counts_line(latest)}). Built {built}. arXiv announces new papers at 20:00 US Eastern time from Sunday to Thursday, and Paperlane rebuilds at 06:00 UTC, after arXiv refreshes its RSS feed at midnight Eastern.

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
  <p class="eyebrow">Listed on <a href="../days/{day['date']}.html#{anchor(p)}">{long_date(day['date'])}</a></p>
</section>
{paper_html(p, day, "../", expanded=True)}"""
    return page(f"{p['title']} | Paperlane", body, "../", built, p["abstract"][:200], base)


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
    (out / "archive.html").write_text(archive_html(days, built, base))
    (out / "paper.html").write_text(lookup_html(built, base))
    (out / "feed.xml").write_text(rss(days, base, built_dt))
    (out / "llms.txt").write_text(llms_txt(days, base, built))
    print(f"Built {len(days)} days into {out}")
