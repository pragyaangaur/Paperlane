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
        f"# {heading or 'Paperlane: new maths papers'}, {long_date(day['date'])}",
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

REPO = "https://github.com/pragyaangaur/Paperlane"

LOGO = (
    '<svg class="mark" viewBox="0 0 40 40" aria-hidden="true">'
    '<rect width="40" height="40" rx="10" class="tile"/>'
    '<path d="M5.5 34.5 Q 9.5 30.5 14 27.5" class="lane"/>'
    '<path d="M32 8.5 L8.5 18.2 L16.6 21.6 Z" class="wing"/>'
    '<path d="M32 8.5 L16.6 21.6 L20.4 31.5 Z" class="body"/></svg>'
)
ICON_SEARCH = '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M13 13l4.5 4.5"/></svg>'
ICON_THEME = '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7"/><path d="M10 3a7 7 0 0 0 0 14z" class="fill"/></svg>'
ICON_CHEVRON = '<svg class="i chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M7 8l3 3 3-3"/></svg>'
ICON_GITHUB = '<svg class="i" viewBox="0 0 16 16" aria-hidden="true"><path class="fill" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.87 2.34.67.07-.52.28-.87.5-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>'

# Runs before the page paints, so a saved theme never flashes the wrong colours.
THEME_BOOT = (
    "<script>try{var t=localStorage.getItem('paperlane-theme');"
    "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}</script>"
)


def short_date(d):
    d = date.fromisoformat(d)
    return f"{d:%a} {d.day} {d:%b}"


def day_stats(day):
    sig = [p.get("signals") or {} for p in day["papers"]]
    return {
        "papers": len(day["papers"]),
        "code": sum(1 for s in sig if s.get("code_links")),
        "lean": sum(1 for s in sig if s.get("lean_repo")),
    }


def page(title, body, prefix, built, description="", base="", kind="page", active=""):
    def nav(href, label, key):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a href="{prefix}{href}"{cur}>{label}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="color-scheme" content="light dark">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
{THEME_BOOT}
<link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<link rel="alternate" type="application/rss+xml" title="Paperlane" href="{prefix}feed.xml">
<link rel="alternate" type="text/markdown" title="Today as Markdown" href="{prefix}latest.md">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"></script>
<script defer src="{prefix}assets/app.js"></script>
</head>
<body class="{kind}" data-prefix="{prefix}" data-base="{esc(base)}">
<header class="site">
  <div class="bar">
    <a class="brand" href="{prefix}index.html" aria-label="Paperlane home">{LOGO}<span>Paperlane</span></a>
    <nav>
      {nav("today.html", "Today", "today")}
      {nav("archive.html", "Archive", "archive")}
      <button type="button" data-open-ask>Ask your AI</button>
      {nav("about.html", "About", "about")}
    </nav>
    <div class="tools">
      <form class="lookup" action="{prefix}paper.html" method="get" role="search">
        {ICON_SEARCH}<input name="id" type="search" placeholder="Open a paper by link or id" aria-label="Open a paper by arXiv link or id" autocomplete="off" spellcheck="false">
      </form>
      <button type="button" class="icon-btn" data-theme-toggle title="Switch theme" aria-label="Switch theme">{ICON_THEME}</button>
      <a class="icon-btn" href="{REPO}" title="Paperlane on GitHub" aria-label="Paperlane on GitHub">{ICON_GITHUB}</a>
    </div>
  </div>
</header>
<main>
{body}
</main>
{ask_dialog(prefix, base)}
<footer class="site">
  <div class="foot">
    <a class="brand small" href="{prefix}index.html">{LOGO}<span>Paperlane</span></a>
    <nav><a href="{prefix}today.html">Today</a><a href="{prefix}archive.html">Archive</a><a href="{prefix}about.html">About</a><a href="{prefix}about.html#agents">For agents</a><a href="{prefix}feed.xml">RSS</a><a href="{REPO}">GitHub</a></nav>
    <p class="built">Updated {esc(built)}</p>
  </div>
</footer>
</body>
</html>
"""


def ask_dialog(prefix, base):
    return f"""<dialog class="ask" id="ask">
  <form method="dialog" class="close"><button aria-label="Close">×</button></form>
  <h2>Let your AI pick today's papers</h2>
  <p>Tell it what you work on. Paperlane writes the prompt, and any assistant that can open web pages does the reading.</p>
  <label for="interests">What do you work on?</label>
  <input id="interests" type="text" placeholder="e.g. extremal graph theory, polyominoes">
  <textarea id="prompt" rows="5" readonly data-base="{esc(base)}"></textarea>
  <div class="row"><button id="copy-prompt" type="button" class="btn primary">Copy prompt</button>
  <a class="muted-link" href="{prefix}about.html#agents">Files for agents →</a></div>
</dialog>"""


def linkify(text):
    """Escape text and turn the URLs in it into links."""
    out, last = [], 0
    for m in signals.URL_RE.finditer(text):
        url = signals._trim(m.group(0))
        href = url if url.lower().startswith("http") else "https://" + url
        out += [esc(text[last : m.start()]), f'<a href="{esc(href)}" rel="nofollow">{esc(url)}</a>']
        last = m.start() + len(url)
    return "".join(out) + esc(text[last:])


def tags(p):
    """The few tags shown on a collapsed row: field, then anything a reader may filter on."""
    s = p.get("signals") or {}
    lead = lead_cat(p)
    out = [f'<span class="tag field">{esc(categories.name(lead))}</span>'] if lead else []
    if section_of(p) == "cross":
        out.append(f'<span class="tag" title="Cross-listed from {esc(p["primary_category"])}">from {esc(p["primary_category"])}</span>')
    if s.get("new_version"):
        out.append(f'<span class="tag version" title="A new version of an older paper">v{p.get("version")}</span>')
    if s.get("lean_repo"):
        out.append('<span class="tag lean" title="A linked repository contains a Lean project">Lean project</span>')
    elif s.get("mentions_lean"):
        out.append('<span class="tag lean-soft" title="Mentions a Lean formalisation">Lean</span>')
    if s.get("code_links"):
        out.append('<span class="tag code">Code</span>')
    return "".join(out)


def details_html(p):
    s = p.get("signals") or {}
    rows = []
    fields = ", ".join(categories.name(c) for c in p.get("math_categories") or [])
    if fields:
        rows.append(("Fields", esc(fields)))
    checks = {c["repo"].lower(): c for c in s.get("github", [])}
    for url in s.get("code_links", []):
        note = ""
        for repo, c in checks.items():
            if f"github.com/{repo}" in url.lower():
                if c["lean"]:
                    note = f' <span class="ok">Lean project found ({esc(", ".join(c["lean_paths"][:2]))})</span>'
                elif c["status"] == "missing":
                    note = ' <span class="warn">repository not found</span>'
        rows.append(("Code", f'<a href="{esc(url)}" rel="nofollow">{esc(short_link(url))}</a>{note}'))
    if p.get("comments"):
        rows.append(("Comments", linkify(p["comments"])))
    if p.get("journal_ref"):
        rows.append(("Journal", esc(p["journal_ref"])))
    return "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)


def paper_html(p, day, prefix="", expanded=False):
    s = p.get("signals") or {}
    authors = p["authors"]
    shown = ", ".join(authors[:6]) + (f" +{len(authors) - 6}" if len(authors) > 6 else "")
    pid = anchor(p)
    attrs = [
        f'id="{pid}"',
        f'data-cats="{" ".join(p.get("math_categories") or [])}"',
        f'data-kind="{section_of(p)}"',
    ]
    if s.get("code_links"):
        attrs.append('data-code="1"')
    if s.get("lean_repo") or s.get("mentions_lean"):
        attrs.append('data-lean="1"')
    return f"""<article class="paper{' open' if expanded else ''}" {' '.join(attrs)}>
  <button type="button" class="head" aria-expanded="{'true' if expanded else 'false'}">
    <span class="title">{esc(p['title'])}</span>
    <span class="authors">{esc(shown)}</span>
    <span class="tags">{tags(p)}</span>
    {ICON_CHEVRON}
  </button>
  <div class="body">
    <p class="abstract">{esc(p['abstract'])}</p>
    <dl class="facts">{details_html(p)}</dl>
    <div class="actions">
      <button type="button" class="btn small" data-act="md" data-md="{prefix}p/{pid}.md" aria-expanded="false">Markdown</button>
      <a class="btn small" href="{p['links']['pdf']}">PDF</a>
      <a class="btn small" href="{prefix}p/{pid}.html">Paper page</a>
      <button type="button" class="btn small ghost" data-act="link" data-url="{prefix}p/{pid}.html">Copy link</button>
      <a class="pid" href="{p['links']['abs']}" title="Open on arXiv">arXiv {esc(p['id'])} ↗</a>
    </div>
    <div class="md-panel" hidden></div>
  </div>
</article>"""


def toolbar_html(day):
    counts = {}
    for p in day["papers"]:
        for c in p.get("math_categories") or []:
            counts[c] = counts.get(c, 0) + 1
    st = day_stats(day)
    lean_any = sum(1 for p in day["papers"] if (p.get("signals") or {}).get("lean_repo") or (p.get("signals") or {}).get("mentions_lean"))
    g = grouped(day)
    subs = "".join(
        f'<label class="opt"><input type="checkbox" name="cat" value="{c}"><span>{esc(categories.name(c))}</span><em>{n}</em></label>'
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    kinds = "".join(
        f'<label class="opt"><input type="checkbox" name="kind" value="{k}" checked><span>{t}</span><em>{len(g[k])}</em></label>'
        for k, t in [("cross", "Cross-lists from other fields"), ("replace", "New versions of older papers")]
        if g[k]
    )
    return f"""<div class="toolbar" id="filters">
  <label class="search">{ICON_SEARCH}<span class="sr">Search these papers</span><input type="search" id="f-q" placeholder="Search titles, authors, abstracts" autocomplete="off"><kbd>/</kbd></label>
  <div class="pop">
    <button type="button" class="chip" id="f-fields" aria-expanded="false" aria-controls="f-panel">Fields <span id="f-fields-n"></span>{ICON_CHEVRON}</button>
    <div class="panel" id="f-panel" hidden>
      <input type="search" id="f-sub" class="mini" placeholder="Find a field" autocomplete="off">
      <div class="sub-list">{subs}</div>
      {f'<p class="panel-label">Also show</p>{kinds}' if kinds else ''}
      <div class="panel-foot"><button type="button" class="link" id="f-none">Clear fields</button><button type="button" class="btn small primary" id="f-done">Done</button></div>
    </div>
  </div>
  <button type="button" class="chip" id="f-code" aria-pressed="false">Has code <em>{st['code']}</em></button>
  <button type="button" class="chip" id="f-lean" aria-pressed="false">Lean <em>{lean_any}</em></button>
</div>
<div class="results"><span id="f-count" aria-live="polite"></span><span id="f-pills"></span><button type="button" class="link" data-clear hidden>Clear all</button></div>"""


def day_html(day, base, built, prefix, newer=None, older=None, is_latest=False):
    g = grouped(day)
    st = day_stats(day)
    sections = []
    labels = {"new": "New papers", "cross": "Cross-listed from other fields", "replace": "New versions"}
    for key, _ in SECTIONS:
        if not g[key]:
            continue
        rows = "\n".join(paper_html(p, day, prefix) for p in g[key])
        sections.append(f'<section class="group" data-group="{key}">\n<h2>{labels[key]} <span class="n">{len(g[key])}</span></h2>\n{rows}\n</section>')
    note = ""
    if day.get("source") == "api-window":
        note = '<span class="note-dot" title="This day was rebuilt from submission times, so it may differ slightly from the announcement and has no new versions.">rebuilt day</span>'
    nav = []
    if older:
        nav.append(f'<a href="{prefix}days/{older}.html">← {short_date(older)}</a>')
    nav.append(f'<a href="{prefix}archive.html">All days</a>')
    if newer:
        nav.append(f'<a href="{prefix}days/{newer}.html">{short_date(newer)} →</a>')
    body = f"""<div class="wrap list">
  <div class="day-head">
    <div>
      <p class="eyebrow">{'Today on Paperlane' if is_latest else 'From the archive'} {note}</p>
      <h1>{long_date(day['date'])}</h1>
      <p class="stats"><b>{st['papers']}</b> papers · <b>{st['code']}</b> with code · <b>{st['lean']}</b> Lean projects</p>
    </div>
    <nav class="day-nav">{''.join(nav)}</nav>
  </div>
  {toolbar_html(day)}
  <p class="empty" id="f-empty" hidden>Nothing matches. <button type="button" class="link" data-clear>Clear the filters</button></p>
  <p class="empty" id="f-lookup" hidden></p>
  {''.join(sections)}
</div>"""
    title = f"Paperlane · {long_date(day['date'])}"
    return page(title, body, prefix, built, f"{st['papers']} new maths papers from {long_date(day['date'])}, with code and Lean tags.", base, "day", "today" if is_latest else "archive")


def home_html(day, days, base, built):
    st = day_stats(day)
    counts = {}
    for p in day["papers"]:
        for c in p.get("math_categories") or []:
            counts[c] = counts.get(c, 0) + 1
    tiles = "".join(
        f'<button type="button" class="tile" data-cat="{c}" aria-pressed="false"><span>{esc(categories.name(c))}</span><em>{n}</em></button>'
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    sample = next((p for p in day["papers"] if (p.get("signals") or {}).get("lean_repo")), day["papers"][0])
    body = f"""<section class="hero">
  <a class="pill-link" href="today.html"><span class="dot"></span>{long_date(day['date'])} · {st['papers']} new papers <span aria-hidden="true">→</span></a>
  <h1>Read today's new maths <br>papers in a minute.</h1>
  <p class="lede">Paperlane gathers each day's new mathematics papers into one calm list. Pick your fields, spot the ones with code or Lean, or hand the whole day to your own AI.</p>
  <form class="big-search" id="home-search" action="today.html" method="get" role="search">
    {ICON_SEARCH}<input name="q" type="search" placeholder="Search today's papers, or paste an arXiv link" aria-label="Search today's papers or paste an arXiv link" autocomplete="off">
    <button type="submit" class="btn primary">Search</button>
  </form>
  <div class="hero-actions"><a class="btn primary big" href="today.html">Browse today's papers</a><button type="button" class="btn big" data-open-ask>Ask your AI</button></div>
</section>

<section class="band" id="fields">
  <div class="band-head">
    <h2>Pick your fields</h2>
    <p>Choose any number. Paperlane remembers them on this device.</p>
  </div>
  <div class="tiles">{tiles}</div>
  <div class="tiles-go"><a class="btn primary" id="fields-go" href="today.html">Show all {st['papers']} papers</a><button type="button" class="link" id="fields-clear" hidden>Clear</button></div>
</section>

<section class="features">
  <div class="feature">
    <p class="kicker">Spotted for you</p>
    <h3>Code and Lean, checked</h3>
    <p>Papers that link to code are tagged. If a linked repository holds a Lean project, the paper gets a green tag. Today: {st['code']} with code, {st['lean']} Lean projects.</p>
    <a href="today.html?lean=1">See the Lean papers →</a>
  </div>
  <div class="feature">
    <p class="kicker">Built for agents</p>
    <h3>Every paper in Markdown</h3>
    <p>Each paper and each day is plain Markdown that any assistant can read. Copy one paper into a chat, or point your agent at the whole day.</p>
    <a href="p/{anchor(sample)}.md">See a paper in Markdown →</a>
  </div>
  <div class="feature">
    <p class="kicker">Any paper</p>
    <h3>Paste a link, start reading</h3>
    <p>Drop any arXiv link or id into the search box. Paperlane opens it with its abstract, its code links and a Markdown copy.</p>
    <a href="paper.html?id={esc(sample['id'])}">Try it →</a>
  </div>
</section>

<section class="promise">
  <p>Paperlane never ranks papers or scores their authors. It shows what can be checked and leaves the choosing to you.</p>
</section>"""
    return page("Paperlane · Read today's new maths papers in a minute", body, "", built,
                "A free daily feed of new mathematics papers for people and their AI agents.", base, "home", "home")


def archive_html(days, built, base):
    rows = []
    for d in days:
        st = day_stats(d)
        rows.append(
            f'<a class="day-row" href="days/{d["date"]}.html"><span class="d">{long_date(d["date"])}</span>'
            f'<span class="c">{st["papers"]} papers</span><span class="c">{st["code"]} with code</span><span class="c">{st["lean"]} Lean</span><span class="go">→</span></a>'
        )
    body = f"""<div class="wrap narrow">
  <p class="eyebrow">Archive</p>
  <h1>Every day on Paperlane</h1>
  <p class="lede small">Each day stays here. To find one paper from any day, paste its link or id into the box at the top.</p>
  <div class="day-list">{''.join(rows)}</div>
</div>"""
    return page("Paperlane · Archive", body, "", built, "Every day of new maths papers on Paperlane.", base, "archive", "archive")


def lookup_html(built, base):
    body = """<div class="wrap narrow">
  <p class="eyebrow" id="lk-eyebrow">Open a paper</p>
  <h1 id="lk-title">Open any paper</h1>
  <p class="lede small" id="lk-status">Paste an arXiv link or id into the box at the top, for example 2610.30655.</p>
  <div id="lk-result"></div>
</div>"""
    return page("Paperlane · Open a paper", body, "", built, "Open any arXiv paper on Paperlane by its link or id.", base, "lookup-page")


def about_html(days, base, built):
    files = [
        ("llms.txt", "A guide to every file, written for language models"),
        ("latest-titles.md", "One line per paper with its id, fields, tags, title and authors"),
        ("latest.md", "The whole day with abstracts"),
        ("latest.json", "The whole day with every field"),
        ("latest/math.CO.md", "One field of the day (swap in any field code)"),
        (f"p/{anchor(days[0]['papers'][0])}.md", "One paper (swap in any arXiv id)"),
        ("feed.xml", "RSS for your feed reader"),
    ]
    rows = "".join(f'<tr><td><a href="{f}"><code>{esc(f)}</code></a></td><td>{esc(t)}</td></tr>' for f, t in files)
    body = f"""<div class="wrap narrow prose">
  <p class="eyebrow">About</p>
  <h1>A calmer way to keep up with maths</h1>
  <p class="lede small">Paperlane collects the new mathematics papers each weekday and puts them in one list that you can filter in seconds. It is free and needs no account.</p>

  <h2>What the tags mean</h2>
  <dl class="glossary">
    <div><dt><span class="tag code">Code</span></dt><dd>The abstract or comments link to a code host such as GitHub or GitLab.</dd></div>
    <div><dt><span class="tag lean">Lean project</span></dt><dd>A linked GitHub repository contains a Lean project file (<code>lean-toolchain</code> or a <code>lakefile</code>). A check that it compiles is planned.</dd></div>
    <div><dt><span class="tag lean-soft">Lean</span></dt><dd>The paper says it is formalised in Lean, but no Lean repository was found.</dd></div>
    <div><dt><span class="tag version">v2</span></dt><dd>A new version of an older paper.</dd></div>
  </dl>
  <p>Every tag comes from a simple check that anyone can repeat. Paperlane never ranks papers or scores authors.</p>

  <h2>When it updates</h2>
  <p>New papers are announced from Sunday to Thursday evening, US Eastern time. Paperlane picks them up at 06:00 UTC the next morning, so a new day appears from Monday to Friday.</p>

  <h2 id="agents">For agents and tools</h2>
  <p>Everything on Paperlane is also published as plain files. Point your assistant at any of these.</p>
  <div class="table-wrap"><table class="files"><tbody>{rows}</tbody></table></div>

  <h2>Where the data comes from</h2>
  <p>Titles, authors, abstracts and categories come from <a href="https://arxiv.org">arXiv</a>, and every paper links to arXiv for the full text. Papers that Paperlane has not listed are looked up through Semantic Scholar or OpenAlex. {ARXIV_THANKS}</p>
  <p>Paperlane is open source on <a href="{REPO}">GitHub</a>, where you can also report a problem or ask for a feature.</p>
</div>"""
    return page("Paperlane · About", body, "", built, "What Paperlane is, what its tags mean and the files it publishes for agents.", base, "about", "about")


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
        f"Listed on Paperlane on {day['date']}. Built {built}. The tags below are checked by code, and the PDF link opens the full paper.",
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
    st = f'Listed on <a href="../days/{day['date']}.html#{anchor(p)}">{long_date(day['date'])}</a>'
    body = f"""<div class="wrap narrow single">
  <p class="eyebrow">{st}</p>
  {paper_html(p, day, "../", expanded=True)}
</div>"""
    return page(f"{p['title']} · Paperlane", body, "../", built, p["abstract"][:200], base, "single")


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
    for i, d in enumerate(days):
        newer = days[i - 1]["date"] if i > 0 else None
        older = days[i + 1]["date"] if i + 1 < len(days) else None
        (out / "days" / f"{d['date']}.html").write_text(day_html(d, base, built, "../", newer, older))
        (out / "days" / f"{d['date']}.md").write_text(day_md(d, base, built))
        (out / "days" / f"{d['date']}.json").write_text(json_day(d, base))

    latest = days[0]
    (out / "index.html").write_text(home_html(latest, days, base, built))
    older = days[1]["date"] if len(days) > 1 else None
    (out / "today.html").write_text(day_html(latest, base, built, "", None, older, is_latest=True))
    (out / "about.html").write_text(about_html(days, base, built))
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
