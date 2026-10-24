"""Render the stored days as a static site: HTML, Markdown, JSON, RSS and llms.txt."""

import html
import json
import re
import urllib.parse
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
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">'
)

# The mark: a written sheet caught in a gust, one line highlighted, the last closed with a tombstone.
LOGO = (
    '<svg class="mark" viewBox="0 0 48 48" aria-hidden="true">'
    '<g class="wind"><path d="M2.6 16.8c2.6.5 4.9.1 7.4-.9"/>'
    '<path d="M.6 27.2c2.8.3 5.2-.4 6.9-2.1 1.8-1.8 1.4-4.6-.7-4.7-2.3-.1-2.9 3-1 4.9 2.1 2.1 5.6 2.1 8.6.6"/>'
    '<path d="M3.4 34.6c2.7.5 5-.2 7.4-1.2"/></g>'
    '<g transform="rotate(-14 29 24)">'
    '<path class="sheet" d="M16.5 8.6c5.3-1.2 10.6 1.1 16.4-.5l5 4.9c-1.6 9.4 1.4 17.9-.6 27.6-6.2 1.6-12.6-1.6-18.6.6-1.8-.2-3.2-1.6-3.1-3.6 1.4-9.4-1.6-19.3.9-29z"/>'
    '<path class="fold" d="M32.9 8.1l.3 5.1 4.7-.2"/><path class="ink" d="M18.7 41.2c.9-1.5 2.4-2 3.9-1.4"/>'
    '<path class="hl" d="M19.6 22.4c4.2-.6 8.6-.4 13.6-.5"/>'
    '<g class="ink"><path d="M20.5 16.6c2.3-1.2 4 .9 6.1-.2 1.9-1 3.3.4 4.9-.3"/><path d="M20.6 22.5c2.8-.9 5 .8 7.6-.1 1.6-.5 2.8 0 4.1-.3"/>'
    '<path d="M20.7 28.5c2.2-.8 4.1.6 6.1-.2"/></g><rect class="qed" x="29.4" y="26.9" width="2.6" height="2.6"/></g></svg>'
)
ICON_GITHUB = '<svg class="i" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.87 2.34.67.07-.52.28-.87.5-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>'

# Light is the default for everyone. Dark only applies when the reader switched to it, and this runs before paint so it never flashes.
THEME_BOOT = (
    "<script>try{if(localStorage.getItem('paperlane-theme')==='dark')document.documentElement.dataset.theme='dark'}catch(e){}</script>"
)
PAGES_RE = re.compile(r"(\d{1,4})\s*(?:pages|pp\b|page)", re.I)


def pages_of(p):
    m = PAGES_RE.search(p.get("comments") or "")
    return int(m.group(1)) if m else None


def short_date(d):
    d = date.fromisoformat(d)
    return f"{d:%a} {d.day} {d:%b}"


def day_stats(day):
    sig = [p.get("signals") or {} for p in day["papers"]]
    return {
        "papers": len(day["papers"]),
        "code": sum(1 for s in sig if s.get("code_links")),
        "lean": sum(1 for s in sig if s.get("lean_repo")),
        "fields": len({c for p in day["papers"] for c in p.get("math_categories") or []}),
    }


def field_counts(day):
    counts = {}
    for p in day["papers"]:
        for c in p.get("math_categories") or []:
            counts[c] = counts.get(c, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


ANALYTICS = {"goatcounter": None}


def analytics_tag():
    """GoatCounter's script when the build has a site code. It sets no cookies."""
    code = ANALYTICS["goatcounter"]
    if not code:
        return ""
    return f'<script data-goatcounter="https://{code}.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'


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
<meta name="color-scheme" content="light">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
{THEME_BOOT}
<link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
{FONTS}
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="alternate" type="application/rss+xml" title="Paperlane" href="{prefix}feed.xml">
<link rel="alternate" type="text/markdown" title="Today as Markdown" href="{prefix}latest.md">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"></script>
<script defer src="{prefix}assets/app.js"></script>
{analytics_tag()}
</head>
<body class="{kind}" data-prefix="{prefix}" data-base="{esc(base)}">
<header class="site">
  <div class="bar">
    <a class="brand" href="{prefix}index.html" aria-label="Paperlane home">{LOGO}<span>Paperlane</span></a>
    <nav class="mono">
      {nav("today.html", "today", "today")}
      {nav("archive.html", "archive", "archive")}
      {nav("ask.html", "ask AI", "ask")}
      {nav("about.html", "about", "about")}
    </nav>
    <div class="tools">
      <form class="lookup mono" action="{prefix}paper.html" method="get" role="search">
        <span aria-hidden="true">&gt;</span><input name="id" type="search" placeholder="open arXiv id or link" aria-label="Open a paper by arXiv link or id" autocomplete="off" spellcheck="false">
      </form>
      <button type="button" class="icon-btn mono" data-theme-toggle title="Dark mode" aria-label="Switch to dark mode">◐</button>
      <a class="icon-btn" href="{REPO}" target="_blank" rel="noopener" title="Source on GitHub" aria-label="Source on GitHub">{ICON_GITHUB}</a>
    </div>
  </div>
</header>
<main>
{body}
</main>
<footer class="site">
  <div class="foot mono">
    <a class="brand small" href="{prefix}index.html">{LOGO}<span>Paperlane</span></a>
    <nav><a href="{prefix}archive.html">archive</a><a href="{prefix}about.html">about</a><a href="{prefix}feed.xml">rss</a><a href="{REPO}">source</a></nav>
    <span class="built">updated {esc(built)}</span>
  </div>
</footer>
</body>
</html>
"""


def ask_html(base, built):
    body = f"""<div class="wrap ask-wrap">
  <header class="issue-head"><p class="kicker mono">ask AI</p>
  <h1>Hand today's papers to <em>your</em> assistant.</h1>
  <p class="lede small">Pick what you want, copy the prompt, and paste it into any assistant that can open web pages.</p></header>
  <section class="ask-builder" id="ask">
    <div class="modes mono" role="tablist">
      <button type="button" role="tab" data-mode="work" aria-selected="true">for my work</button>
      <button type="button" role="tab" data-mode="curious" aria-selected="false">just curious</button>
      <button type="button" role="tab" data-mode="routine" aria-selected="false">every morning</button>
    </div>
    <div id="ask-time" class="time-row" hidden>
      <label for="routine-time" class="mono">run every weekday at</label>
      <div class="time-line"><input id="routine-time" type="time" value="07:30" step="300" aria-label="Time">
      <div class="tz" id="tz"><input type="hidden" id="routine-tz">
        <button type="button" class="tz-btn" aria-haspopup="listbox" aria-expanded="false" aria-label="Timezone"><span class="tz-name"></span><span class="tz-off mono"></span><span class="tz-caret" aria-hidden="true">▾</span></button>
        <div class="tz-pop" hidden>
          <input type="search" class="tz-q" placeholder="Search a city or country" autocomplete="off" spellcheck="false" aria-label="Search timezones">
          <ul class="tz-list" role="listbox" aria-label="Timezones"></ul>
        </div>
      </div></div>
      <p class="hint mono" id="time-hint"></p>
    </div>
    <div id="ask-work"><label for="interests" class="mono">what do you work on?</label>
    <input id="interests" class="interest-input" type="text" placeholder="extremal graph theory, polyominoes" autocomplete="off" data-interests></div>
    <pre class="terminal" id="prompt" data-base="{esc(base)}"></pre>
    <div class="ask-actions">
      <button id="copy-prompt" type="button" class="btn primary">Copy prompt</button>
      <p class="mono hint" id="ask-note">Nothing you type here leaves your browser.</p>
    </div>
  </section>
</div>"""
    return page("Ask your AI · Paperlane", body, "", built, "Hand today's new maths papers to your own AI assistant with one prompt.", base, "ask-page", "ask")


def linkify(text):
    """Escape text and turn the URLs in it into links."""
    out, last = [], 0
    for m in signals.URL_RE.finditer(text):
        url = signals._trim(m.group(0))
        href = url if url.lower().startswith("http") else "https://" + url
        out += [esc(text[last : m.start()]), f'<a href="{esc(href)}" target="_blank" rel="nofollow noopener">{esc(url)}</a>']
        last = m.start() + len(url)
    return "".join(out) + esc(text[last:])


def authors_text(authors, limit=6):
    if len(authors) <= 2:
        return " and ".join(authors)
    shown = authors[:limit]
    rest = len(authors) - len(shown)
    if rest:
        return ", ".join(shown) + f" and {rest} more"
    return ", ".join(shown[:-1]) + " and " + shown[-1]


def tags(p):
    """One quiet line of metadata: main field, origin, signals, length."""
    s = p.get("signals") or {}
    out = [f'<span class="t-field" title="{esc(categories.name(c))}">{esc(c)}</span>' for c in (p.get("math_categories") or [])[:1]]
    if section_of(p) == "cross":
        out.append(f'<span title="Cross-listed from another field">via {esc(p["primary_category"])}</span>')
    if s.get("new_version"):
        out.append(f'<span class="t-rev" title="A revised version of an older paper">v{p.get("version")}</span>')
    if s.get("code_links"):
        out.append('<span class="t-code" title="Links to code">code</span>')
    if s.get("lean_repo"):
        out.append('<span class="t-lean" title="A linked repository contains a Lean project">∎ lean</span>')
    elif s.get("mentions_lean"):
        out.append('<span class="t-lean soft" title="Mentions a Lean formalisation, no repository found">□ lean</span>')
    n = pages_of(p)
    if n:
        out.append(f'<span class="t-pp">{n} pp</span>')
    return '<span class="sep"> · </span>'.join(out)


def details_html(p):
    s = p.get("signals") or {}
    rows = []
    checks = {c["repo"].lower(): c for c in s.get("github", [])}
    for url in s.get("code_links", []):
        note = ""
        for repo, c in checks.items():
            if f"github.com/{repo}" in url.lower():
                if c["lean"]:
                    note = f' <span class="ok">∎ Lean project ({esc(", ".join(c["lean_paths"][:2]))})</span>'
                elif c["status"] == "missing":
                    note = ' <span class="warn">repository not found</span>'
        rows.append(("code", f'<a href="{esc(url)}" target="_blank" rel="nofollow noopener">{esc(short_link(url))}</a>{note}'))
    if p.get("comments"):
        rows.append(("comments", linkify(p["comments"])))
    if p.get("journal_ref"):
        rows.append(("journal", esc(p["journal_ref"])))
    fields = ", ".join(f"{categories.name(c)}" for c in p.get("math_categories") or [])
    if fields:
        rows.append(("fields", esc(fields)))
    return "".join(f'<div><dt class="mono">{k}</dt><dd>{v}</dd></div>' for k, v in rows)


def actions_html(p, prefix, pid):
    return f"""<div class="actions mono">
      <button type="button" class="act" data-act="md" data-md="{prefix}p/{pid}.md" aria-expanded="false">markdown</button>
      <a class="act" href="{p['links']['pdf']}" target="_blank" rel="noopener">pdf ↗</a>
      <a class="act" href="{prefix}p/{pid}.html">page</a>
      <button type="button" class="act" data-act="link" data-url="{prefix}p/{pid}.html">copy link</button>
      <a class="pid" href="{p['links']['abs']}" target="_blank" rel="noopener" title="Open on arXiv">arXiv:{esc(p['id'])} ↗</a>
    </div>
    <div class="md-panel" hidden></div>"""


def paper_html(p, day, prefix="", order=0):
    s = p.get("signals") or {}
    pid = anchor(p)
    attrs = [
        f'id="{pid}"',
        f'data-cats="{" ".join(p.get("math_categories") or [])}"',
        f'data-kind="{section_of(p)}"',
        f'data-order="{order}"',
    ]
    if s.get("code_links"):
        attrs.append('data-code="1"')
    if s.get("lean_repo") or s.get("mentions_lean"):
        attrs.append('data-lean="1"')
    n = pages_of(p)
    if n:
        attrs.append(f'data-pages="{n}"')
    return f"""<article class="paper" {' '.join(attrs)}>
  <button type="button" class="head" aria-expanded="false">
    <span class="num mono" aria-hidden="true"></span>
    <span class="title">{esc(p['title'])}</span>
    <span class="authors">{esc(authors_text(p['authors']))}</span>
    <span class="tags mono" data-fields="{esc(' '.join(categories.name(c) for c in p.get('math_categories') or []))}">{tags(p)}</span>
    <span class="why mono" hidden></span>
  </button>
  <div class="body">
    <p class="abstract">{esc(p['abstract'])}</p>
    <dl class="facts">{details_html(p)}</dl>
    {actions_html(p, prefix, pid)}
  </div>
</article>"""


def toolbar_html(day):
    g = grouped(day)
    st = day_stats(day)
    lean_any = sum(1 for p in day["papers"] if (p.get("signals") or {}).get("lean_repo") or (p.get("signals") or {}).get("mentions_lean"))
    subs = "".join(
        f'<label class="opt"><input type="checkbox" name="cat" value="{c}"><span>{esc(categories.name(c))}</span><i class="leader"></i><em class="mono">{n}</em></label>'
        for c, n in field_counts(day)
    )
    kinds = "".join(
        f'<label class="opt"><input type="checkbox" name="kind" value="{k}" checked><span>{t}</span><i class="leader"></i><em class="mono">{len(g[k])}</em></label>'
        for k, t in [("cross", "Cross-lists from other subjects"), ("replace", "Revised papers")]
        if g[k]
    )
    return f"""<div class="toolbar" id="filters">
  <div class="row1">
    <label class="search"><span class="mono prompt" aria-hidden="true">/</span><span class="sr">Search these papers</span><input type="search" id="f-q" placeholder="Search, or describe what you work on" autocomplete="off"></label>
    <div class="pop">
      <button type="button" class="chip" id="f-fields" aria-expanded="false" aria-controls="f-panel">Fields<span id="f-fields-n" class="mono"></span></button>
      <div class="panel" id="f-panel" hidden>
        <input type="search" id="f-sub" class="mini" placeholder="Find a field" autocomplete="off">
        <div class="sub-list">{subs}</div>
        {f'<p class="panel-label mono">also show</p>{kinds}' if kinds else ''}
        <div class="panel-foot"><button type="button" class="link mono" id="f-none">clear fields</button><button type="button" class="btn small primary" id="f-done">Done</button></div>
      </div>
    </div>
    <button type="button" class="chip" id="f-code" aria-pressed="false">Code <em class="mono">{st['code']}</em></button>
    <button type="button" class="chip lean" id="f-lean" aria-pressed="false">∎ Lean <em class="mono">{lean_any}</em></button>
  </div>
</div>
<div class="results mono"><span id="f-count" aria-live="polite"></span><span id="f-pills"></span><button type="button" class="link" data-clear hidden>clear</button>
  <label class="sort"><span class="sr">Order</span><select id="f-sort"><option value="field">by field</option><option value="newest">newest</option><option value="short">shortest</option></select></label></div>"""


def day_html(day, base, built, prefix, number, newer=None, older=None, is_latest=False):
    st = day_stats(day)
    groups, order = {}, 0
    revised = []
    for p in sorted(day["papers"], key=lambda p: p["id"]):
        if section_of(p) == "replace":
            revised.append(p)
        else:
            groups.setdefault(lead_cat(p) or "other", []).append(p)
    sections = []
    for cat, _ in sorted(groups.items(), key=lambda kv: (-len(kv[1]), categories.name(kv[0]))):
        rows = []
        for p in groups[cat]:
            rows.append(paper_html(p, day, prefix, order))
            order += 1
        sections.append(
            f'<section class="group" id="g-{cat}" data-field="{cat}"><h2><span>{esc(categories.name(cat))}</span><i class="leader"></i><span class="n mono">{len(groups[cat])}</span></h2>\n'
            + "\n".join(rows) + '\n<button type="button" class="more mono" hidden></button>\n</section>'
        )
    if revised:
        rows = []
        for p in revised:
            rows.append(paper_html(p, day, prefix, order))
            order += 1
        sections.append(
            f'<section class="group" id="g-revised" data-field="_rev"><h2><span>Revised papers</span><i class="leader"></i><span class="n mono">{len(revised)}</span></h2>\n'
            + "\n".join(rows) + '\n<button type="button" class="more mono" hidden></button>\n</section>'
        )
    rebuilt = ""
    if day.get("source") == "api-window":
        rebuilt = ' · <span class="rebuilt" title="Rebuilt from submission times, so it may differ slightly from the announcement and has no revised papers.">rebuilt</span>'
    nav = []
    if older:
        nav.append(f'<a href="{prefix}days/{older}.html">← {short_date(older)}</a>')
    nav.append(f'<a href="{prefix}archive.html">archive</a>')
    if newer:
        nav.append(f'<a href="{prefix}days/{newer}.html">{short_date(newer)} →</a>')
    d = date.fromisoformat(day["date"])
    body = f"""<div class="wrap">
  <header class="issue-head">
    <p class="kicker mono">no. {number} · {'today' if is_latest else 'from the archive'}{rebuilt}<span class="day-nav">{' '.join(nav)}</span></p>
    <h1>{d:%A}, <em>{d.day} {d:%B %Y}</em></h1>
    <p class="stats mono">{st['papers']} papers in {st['fields']} fields</p>
  </header>
  {toolbar_html(day)}
  <p class="empty" id="f-empty" hidden>Nothing matches. <button type="button" class="link" data-clear>Clear the filters</button></p>
  <p class="empty" id="f-lookup" hidden></p>
  <div id="list">
  {''.join(sections)}
  </div>
  <section class="group flat" id="flat" hidden></section>
  <button type="button" class="more mono" id="flat-more" hidden></button>
</div>"""
    title = f"{d:%A} {d.day} {d:%B %Y} · Paperlane"
    return page(title, body, prefix, built, f"{st['papers']} new maths papers from {long_date(day['date'])}, with code and Lean tags.", base, "day", "today" if is_latest else "archive")


CURIOUS_PROMPT = (
    "Read {base}/latest-titles.md, the list of new maths papers from the latest Paperlane issue. "
    "Pick the two results a curious person with no maths degree would find most surprising, read their abstracts in "
    "{base}/latest.md, and explain each one in plain words with an everyday example."
)


# Things a newcomer might type. The home page offers the ones that match something in the issue.
TRY_WORDS = [
    ("prime numbers", r"\bprimes?\b"), ("knots", r"\bknots?\b"), ("black holes", r"\bblack holes?\b"),
    ("random walks", r"\brandom walks?\b"), ("games", r"\bgames?\b"), ("infinity", r"\binfinit"),
    ("symmetry", r"\bsymmetr"), ("chaos", r"\bchao"), ("fluids", r"\bfluids?\b"), ("neural networks", r"\bneural network"),
    ("quantum", r"\bquantum\b"), ("shapes", r"\bshapes?\b"), ("graphs", r"\bgraphs?\b"),
]


def try_words(day, limit=6):
    text = [(p["title"] + " " + p["abstract"]).lower() for p in day["papers"]]
    found = [w for w, pat in TRY_WORDS if sum(1 for t in text if re.search(pat, t)) >= 2]
    return found[:limit]


def home_html(day, number, base, built, fresh):
    st = day_stats(day)
    d = date.fromisoformat(day["date"])
    when = "last night" if fresh else f"on {d:%A}"
    words = try_words(day)
    chips = "".join(f'<button type="button" data-try="{esc(w)}">{esc(w)}</button>' for w in words)
    curious = esc(CURIOUS_PROMPT.format(base=base))
    body = f"""<section class="hero wrap">
  <a class="live" href="today.html"><span class="pulse" aria-hidden="true"></span><span class="mono">issue no. {number} · {d:%a} {d.day} {d:%b}</span></a>
  <h1>{st['papers']} new maths papers came out {when}.<br><em>What are you curious about?</em></h1>
  <div class="finder" id="finder">
    <label class="finder-box"><span class="sr">Find papers in this issue</span>
      <input id="finder-q" type="search" placeholder="Type a topic or a word" autocomplete="off" spellcheck="false" enterkeyhint="search"></label>
    {f'<p class="tries mono"><span>try</span>{chips}</p>' if chips else ''}
    <ol class="finds" id="finds" aria-live="polite"></ol>
    <p class="finds-foot mono" id="finds-foot" hidden><a id="finds-all" href="today.html"></a><a id="finds-ai" href="ask.html"></a></p>
  </div>
  <p class="browse mono"><a href="today.html">or browse all {st['papers']} papers →</a></p>
</section>

<section class="hook wrap">
  <p class="kicker mono">no maths degree needed</p>
  <h2>Let your AI <em>explain them</em>.</h2>
  <p>The assistant you already use can read the whole issue in seconds. Paste this in and hear what mathematicians found {when}, in plain words.</p>
  <pre class="terminal prompt-box" id="curious-prompt">{curious}</pre>
  <p class="hook-actions"><button type="button" class="btn primary" data-copy-from="#curious-prompt">Copy prompt</button><a class="mono" href="ask.html">more prompts →</a></p>
</section>"""
    return page(f"Paperlane · {st['papers']} new maths papers {when}", body, "", built,
                "Every night's new mathematics papers in one short issue that you can search in seconds and your AI assistant can read for you.", base, "home", "home")


def archive_html(days, numbers, built, base):
    rows = []
    for d in days:
        st = day_stats(d)
        dd = date.fromisoformat(d["date"])
        rows.append(
            f'<li><a href="days/{d["date"]}.html"><span class="mono no">no. {numbers[d["date"]]}</span>'
            f'<span class="d">{dd:%A}, <em>{dd.day} {dd:%B %Y}</em></span><i class="leader"></i>'
            f'<span class="mono c">{st["papers"]} papers · {st["lean"]} ∎</span></a></li>'
        )
    body = f"""<div class="wrap narrow">
  <header class="issue-head"><p class="kicker mono">archive</p><h1>Every issue, <em>so far</em></h1>
  <p class="lede small">Each day stays here. To open one paper from any day, paste its arXiv link or id into the box at the top.</p></header>
  <ol class="toc archive-toc">{''.join(rows)}</ol>
</div>"""
    return page("Archive · Paperlane", body, "", built, "Every issue of Paperlane.", base, "archive", "archive")


def lookup_html(built, base):
    body = """<div class="wrap narrow">
  <article class="first-page" id="lk-page">
    <p class="kicker mono" id="lk-eyebrow">open a paper</p>
    <h1 id="lk-title">Open any paper</h1>
    <p class="lede small" id="lk-status">Paste an arXiv link or id into the box at the top, for example 2610.30655.</p>
    <div id="lk-result"></div>
  </article>
</div>"""
    return page("Open a paper · Paperlane", body, "", built, "Open any arXiv paper on Paperlane by its link or id.", base, "lookup-page")


def about_html(days, base, built):
    files = [
        ("llms.txt", "A guide to every file, written for language models"),
        ("latest-titles.md", "One line per paper: id, fields, tags, title, authors"),
        ("latest.md", "The whole day with abstracts"),
        ("latest.json", "The whole day with every field"),
        ("latest/math.CO.md", "One field of the day (swap in any field code)"),
        (f"p/{anchor(days[0]['papers'][0])}.md", "One paper (swap in any arXiv id)"),
        ("feed.xml", "RSS for your feed reader"),
    ]
    rows = "".join(f'<tr><td class="mono"><a href="{f}">{esc(f)}</a></td><td>{esc(t)}</td></tr>' for f, t in files)
    body = f"""<div class="wrap narrow prose">
  <header class="issue-head"><p class="kicker mono">about</p><h1>A quieter way to <em>keep up with mathematics</em></h1></header>
  <p class="lede small">Paperlane collects the new mathematics papers every weekday and sets them in one list that you can make your own in seconds. It is free and needs no account.</p>

  <h2>How search works</h2>
  <p>Type a topic, a phrase or a name and Paperlane ranks the papers with BM25, the standard formula behind most search engines, over titles, abstracts and authors. Titles count twice, exact phrases get a bonus, and British and American spellings match each other. Only papers that match are shown, best first, with the words that matched under each one. This runs in your browser and nothing you type is sent anywhere.</p>
  <p>With no search, papers sit under their main field, largest field first, and the fields you picked move to the top. You can also list them newest first or shortest first. Paperlane never ranks a paper by who wrote it.</p>

  <h2>Why not just ask your AI to read arXiv?</h2>
  <p>One night of mathematics is about 57,000 words of abstracts, the length of a short novel. Paperlane reads it once and hands your assistant an index of about 7,500 words, so the answer is fast and cheap. Some answers also need real work, such as checking every linked repository for a Lean project, and Paperlane does that once for everyone. Every issue stays in the archive, so you can look back and see when a paper was revised.</p>

  <h2>What the tags mean</h2>
  <dl class="glossary">
    <div><dt class="mono t-lean">∎ lean</dt><dd>A linked GitHub repository contains a Lean project file (<code>lean-toolchain</code> or a <code>lakefile</code>). A check that it compiles is planned.</dd></div>
    <div><dt class="mono t-lean soft">□ lean</dt><dd>The paper says it is formalised in Lean, but no Lean repository was found.</dd></div>
    <div><dt class="mono t-code">code</dt><dd>The abstract or comments link to a code host such as GitHub or GitLab.</dd></div>
    <div><dt class="mono t-rev">v2</dt><dd>A revised version of an older paper.</dd></div>
    <div><dt class="mono">via cs.CC</dt><dd>A paper from another subject that its authors also listed under mathematics.</dd></div>
  </dl>
  <p>Every tag comes from a simple check that anyone can repeat. Paperlane never ranks papers or scores authors.</p>

  <h2>When it updates</h2>
  <p>New papers are announced from Sunday to Thursday evening, US Eastern time. Paperlane picks them up at 06:00 UTC the next morning, so a new issue appears from Monday to Friday.</p>

  <h2 id="agents">For agents and tools</h2>
  <p>Everything on Paperlane is also published as plain files. Point your assistant at any of these.</p>
  <div class="table-wrap"><table class="files"><tbody>{rows}</tbody></table></div>

  <h2>Privacy</h2>
  <p>Paperlane counts visits with GoatCounter, which sets no cookies and stores no personal data. It also counts a few anonymous events, such as a prompt being copied or a Markdown file being opened, to learn which features people use. Your fields and interests are kept in your own browser and are never sent anywhere.</p>

  <h2>Where the data comes from</h2>
  <p>Titles, authors, abstracts and categories come from <a href="https://arxiv.org" target="_blank" rel="noopener">arXiv</a>, and every paper links to arXiv for the full text. Papers that Paperlane has not listed are looked up through Semantic Scholar or OpenAlex. {ARXIV_THANKS}</p>
  <p>Paperlane is open source on <a href="{REPO}">GitHub</a>, where you can report a problem or ask for a feature.</p>
</div>"""
    return page("About · Paperlane", body, "", built, "How Paperlane orders papers, what its tags mean and the files it publishes for agents.", base, "about", "about")


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


def single_html(p, day, base, built, number):
    pid = anchor(p)
    s = p.get("signals") or {}
    attrs = f'id="{pid}" data-cats="{" ".join(p.get("math_categories") or [])}"'
    body = f"""<div class="wrap narrow">
  <article class="first-page paper open" {attrs}>
    <p class="kicker mono">no. {number} · <a href="../days/{day['date']}.html#{pid}">{long_date(day['date'])}</a></p>
    <h1 class="title">{esc(p['title'])}</h1>
    <p class="authors">{esc(authors_text(p['authors'], 12))}</p>
    <p class="tags mono">{tags(p)}</p>
    <h2 class="abs-h">Abstract</h2>
    <p class="abstract">{esc(p['abstract'])}</p>
    <dl class="facts">{details_html(p)}</dl>
    {actions_html(p, "../", pid)}
  </article>
</div>"""
    return page(f"{p['title']} · Paperlane", body, "../", built, p["abstract"][:200], base, "single")


def json_day(day, base):
    out = dict(day)
    out["papers"] = [dict(p, paperlane_url=paper_url(base, day, p)) for p in day["papers"]]
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def build(days, out, base, built_dt=None, goatcounter=None):
    """Write the whole site for `days` (newest first) into `out`."""
    code = (goatcounter or "").strip().lower()
    ANALYTICS["goatcounter"] = code if re.fullmatch(r"[a-z0-9-]{2,50}", code) else None
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
    numbers = {d["date"]: len(days) - i for i, d in enumerate(days)}
    for d in reversed(days):
        for p in d["papers"]:
            (out / "p" / f"{anchor(p)}.md").write_text(single_md(p, base, d, built))
            (out / "p" / f"{anchor(p)}.html").write_text(single_html(p, d, base, built, numbers[d["date"]]))
    for i, d in enumerate(days):
        newer = days[i - 1]["date"] if i > 0 else None
        older = days[i + 1]["date"] if i + 1 < len(days) else None
        (out / "days" / f"{d['date']}.html").write_text(day_html(d, base, built, "../", numbers[d["date"]], newer, older))
        (out / "days" / f"{d['date']}.md").write_text(day_md(d, base, built))
        (out / "days" / f"{d['date']}.json").write_text(json_day(d, base))

    latest = days[0]
    titles = titles_md(latest, base, built)
    fresh = (built_dt.date() - date.fromisoformat(latest["date"])).days <= 1
    (out / "index.html").write_text(home_html(latest, numbers[latest["date"]], base, built, fresh))
    older = days[1]["date"] if len(days) > 1 else None
    (out / "today.html").write_text(day_html(latest, base, built, "", numbers[latest["date"]], None, older, is_latest=True))
    (out / "about.html").write_text(about_html(days, base, built))
    (out / "latest.md").write_text(day_md(latest, base, built))
    (out / "latest.json").write_text(json_day(latest, base))
    (out / "latest-titles.md").write_text(titles)
    for c in sorted({c for p in latest["papers"] for c in p.get("math_categories") or []}):
        sel = [p for p in latest["papers"] if c in (p.get("math_categories") or [])]
        (out / "latest" / f"{c}.md").write_text(day_md(latest, base, built, sel, f"Paperlane: {categories.name(c)} ({c})"))
    (out / "archive.html").write_text(archive_html(days, numbers, built, base))
    (out / "paper.html").write_text(lookup_html(built, base))
    (out / "ask.html").write_text(ask_html(base, built))
    (out / "feed.xml").write_text(rss(days, base, built_dt))
    (out / "llms.txt").write_text(llms_txt(days, base, built))
    print(f"Built {len(days)} days into {out}")
