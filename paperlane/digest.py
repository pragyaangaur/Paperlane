"""The daily email: one short issue sent as a Kit broadcast.

The email is short on purpose. It carries no abstracts and sends every reader into the issue. It is written in Markdown and sent as HTML. Kit's default template wraps
it, adds the unsubscribe link and sends it to every subscriber.
"""

import json
import re
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from . import USER_AGENT, categories, leancheck

API = "https://api.kit.com/v4/broadcasts"
MAX_LEAN = 4
MAX_FIELDS = 4
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
    """(subject, body) for one issue.

    The email is a teaser. It names the numbers, the papers whose Lean proofs compile and the
    busiest fields, and every link leads into the issue on Paperlane, where the reading happens.
    """
    from . import render  # render imports this module, so import late

    papers = day["papers"]
    fresh = [p for p in papers if is_new(p)]
    issue = f"{base}/days/{day['date']}.html"
    lean = [p for p in papers if (p.get("signals") or {}).get("lean_repo")]
    built = sorted((p for p in lean if (leancheck.build_of(p) or {}).get("status") == "builds"),
                   key=lambda p: (not is_new(p), p["id"]))

    subject = f"{len(fresh)} new maths papers came out last night"
    if built:
        subject += f", {len(built)} with proofs that compile"
    out = [
        f"**{len(fresh)} new maths papers came out last night.** One of them is probably the paper you would want to read first.",
        "",
        f"**{md_link(f'Find yours in issue no. {number} →', issue)}**",
    ]

    if built:
        one = len(built) == 1
        out += ["", f"**{len(built)} {'comes with a Lean proof that compiles' if one else 'come with Lean proofs that compile'}.** "
                    f"Paperlane built {'it' if one else 'each one'} on a clean machine.", ""]
        out += [f"- {md_link(plain(p['title']), paper_link(p, base))}" for p in built[:MAX_LEAN]]
        if len(built) > MAX_LEAN:
            out += ["", md_link(f"See all {len(built)} →", issue + "?lean=1")]
    elif lean:
        out += ["", f"**{len(lean)} link a Lean formalisation.** {md_link('See them →', issue + '?lean=1')}"]

    fields = render.field_counts(day)
    top = " · ".join(md_link(f"{categories.name(c)} {n}", f"{issue}?cat={c}") for c, n in fields[:MAX_FIELDS])
    more = f" · {md_link(f'{len(fields) - MAX_FIELDS} more fields', issue)}" if len(fields) > MAX_FIELDS else ""
    out += ["", f"**Busiest fields:** {top}{more}"]

    words = render.try_words(day, 4)
    if words:
        out += ["", "**Try searching:** " + " · ".join(md_link(w, f"{issue}?q={urllib.parse.quote(w)}") for w in words)]

    out += ["", md_link("Not a mathematician? Let your AI explain the two most surprising results →", f"{base}/ask.html?mode=curious")]
    if lean:
        out += ["", md_link("Every Lean project Paperlane has built →", f"{base}/lean.html")]
    out += ["", "---", "",
            "Reply to this email to tell me what would make it more useful. I read every reply.  ",
            "Pragyaan, who builds Paperlane",
            "", f"Paperlane is a free daily list of new arXiv mathematics papers. {render.ARXIV_THANKS}"]
    return subject, tagged("\n".join(out) + "\n", base)


def tagged(body, base):
    """Mark every Paperlane link as coming from the email, which GoatCounter reads as the referrer."""
    def add(m):
        url = m.group(1)
        return f"]({url}{'&' if '?' in url else '?'}utm_source=email)"
    return re.sub(r"\]\((" + re.escape(base) + r"[^)\s]*)\)", add, body)


INK, INK2, MUTED, RULE, PAPER, LIME, HL = "#111210", "#3a3b36", "#7a7d73", "#e3e5dd", "#fdfdfc", "#c8f53c", "#d9f763"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"
MONO = "'SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"


def html_email(day, number, base):
    """The same issue as markdown(), laid out as an HTML email with a header image and simple graphics.

    Email clients ignore stylesheets, so every style is inline and the layout uses tables.
    """
    import html as h
    from . import render

    def esc(t):
        return h.escape(t, quote=True)

    def url(u):
        return u + ("&" if "?" in u else "?") + "utm_source=email"

    def a(text, href, style=""):
        return f'<a href="{esc(url(href))}" style="color:{INK};{style}">{text}</a>'

    papers = day["papers"]
    fresh = [p for p in papers if is_new(p)]
    updated = len(papers) - len(fresh)
    issue = f"{base}/days/{day['date']}.html"
    lean = [p for p in papers if (p.get("signals") or {}).get("lean_repo")]
    built = sorted((p for p in lean if (leancheck.build_of(p) or {}).get("status") == "builds"),
                   key=lambda p: (not is_new(p), p["id"]))
    d = date.fromisoformat(day["date"])
    when = f"{d:%A} {d.day} {d:%B %Y}"

    def tile(n, label):
        return (f'<td width="33%" style="padding:0 5px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="border:1px solid {RULE};border-radius:10px;background:#ffffff;"><tr><td style="padding:14px 14px 12px;">'
                f'<div style="font-family:{SANS};font-size:28px;font-weight:700;letter-spacing:-0.02em;color:{INK};line-height:1;">{n}</div>'
                f'<div style="font-family:{MONO};font-size:11px;color:{MUTED};margin-top:6px;">{label}</div></td></tr></table></td>')

    out = []
    out.append(f'<a href="{esc(url(base + "/"))}"><img src="{base}/assets/email-header.png" width="600" alt="Paperlane: new maths papers, every weekday morning" '
               f'style="display:block;width:100%;max-width:600px;height:auto;border:0;"></a>')
    out.append(f'<p style="font-family:{MONO};font-size:12px;color:{MUTED};margin:26px 0 8px;letter-spacing:0.02em;">ISSUE NO. {number} · {esc(when.upper())}</p>')
    out.append(f'<h1 style="font-family:{SANS};font-size:30px;line-height:1.15;font-weight:700;letter-spacing:-0.025em;color:{INK};margin:0 0 6px;">'
               f'{len(fresh)} new maths papers came out last night.</h1>')
    out.append(f'<p style="font-family:{SERIF};font-style:italic;font-size:22px;color:{INK};margin:0 0 22px;">'
               f'<span style="background:{HL};padding:0 4px;">One of them is probably yours.</span></p>')
    out.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 -5px 24px;"><tr>'
               f'{tile(len(fresh), "new papers")}{tile(updated, "updated papers")}{tile(len(built), "Lean proofs build")}</tr></table>')
    out.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 30px;"><tr><td style="background:{LIME};border-radius:999px;border:2px solid {INK};">'
               f'<a href="{esc(url(issue))}" style="display:inline-block;padding:13px 26px;font-family:{SANS};font-size:16px;font-weight:700;color:{INK};text-decoration:none;">'
               f'Find yours in issue no. {number} &rarr;</a></td></tr></table>')

    def heading(t):
        return (f'<p style="font-family:{MONO};font-size:12px;color:{MUTED};margin:0 0 10px;padding-top:18px;border-top:1px solid {RULE};'
                f'letter-spacing:0.02em;">{t}</p>')

    if built:
        out.append(heading(f"∎ {len(built)} LEAN PROOF{'S' if len(built) != 1 else ''} THAT COMPILE"))
        out.append(f'<p style="font-family:{SANS};font-size:14px;color:{INK2};margin:0 0 12px;">Paperlane cloned each project and ran <code>lake build</code> on a clean machine.</p>')
        for p in built[:MAX_LEAN]:
            out.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 10px;border-left:4px solid {LIME};background:#ffffff;">'
                       f'<tr><td style="padding:10px 14px;">'
                       f'{a(esc(plain(p["title"])), paper_link(p, base), f"font-family:{SERIF};font-size:17px;line-height:1.35;text-decoration:none;")}'
                       f'<div style="font-family:{MONO};font-size:11px;color:{MUTED};margin-top:5px;">{esc(authors(p.get("authors")))} · '
                       f'<span style="background:{HL};color:{INK};padding:1px 5px;">∎ lean builds</span></div></td></tr></table>')
        if len(built) > MAX_LEAN:
            out.append(f'<p style="font-family:{SANS};font-size:14px;margin:4px 0 0;">{a(f"See all {len(built)} &rarr;", issue + "?lean=1")}</p>')
        out.append('<div style="height:18px;"></div>')
    elif lean:
        out.append(heading(f"∎ {len(lean)} LINK A LEAN FORMALISATION"))
        out.append(f'<p style="font-family:{SANS};font-size:14px;margin:0 0 24px;">{a("See them &rarr;", issue + "?lean=1")}</p>')

    fields = render.field_counts(day)
    if fields:
        out.append(heading("BUSIEST FIELDS"))
        top = max(n for _, n in fields[:5])
        for c, n in fields[:5]:
            w = max(4, round(100 * n / top))
            out.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 7px;"><tr>'
                       f'<td width="42%" style="font-family:{SANS};font-size:14px;padding-right:10px;">{a(esc(categories.name(c)), f"{issue}?cat={c}", "text-decoration:none;")}</td>'
                       f'<td><table role="presentation" width="{w}%" cellpadding="0" cellspacing="0"><tr><td style="background:{HL};height:14px;border-radius:3px;font-size:0;line-height:0;">&nbsp;</td></tr></table></td>'
                       f'<td width="40" align="right" style="font-family:{MONO};font-size:12px;color:{MUTED};">{n}</td></tr></table>')
        if len(fields) > 5:
            out.append(f'<p style="font-family:{SANS};font-size:13px;margin:8px 0 0;">{a(f"{len(fields) - 5} more fields &rarr;", issue, f"color:{MUTED};")}</p>')
        out.append('<div style="height:18px;"></div>')

    words = render.try_words(day, 5)
    if words:
        out.append(heading("TRY SEARCHING"))
        chips = "".join(f'<a href="{esc(url(f"{issue}?q={urllib.parse.quote(w)}"))}" style="display:inline-block;margin:0 6px 8px 0;padding:6px 12px;'
                        f'border:1px solid {RULE};border-radius:999px;font-family:{MONO};font-size:13px;color:{INK};text-decoration:none;background:#ffffff;">{esc(w)}</a>'
                        for w in words)
        out.append(f'<p style="margin:0 0 22px;">{chips}</p>')

    out.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 26px;background:{INK};border-radius:12px;"><tr><td style="padding:18px 20px;">'
               f'<p style="font-family:{SANS};font-size:16px;font-weight:700;color:{PAPER};margin:0 0 4px;">Not a mathematician?</p>'
               f'<p style="font-family:{SANS};font-size:14px;color:#c4c7bd;margin:0 0 12px;">Copy one prompt and let your AI explain the two most surprising results in plain words.</p>'
               f'<a href="{esc(url(base + "/ask.html?mode=curious"))}" style="font-family:{SANS};font-size:14px;font-weight:700;color:{LIME};">Get the prompt &rarr;</a>'
               f'</td></tr></table>')
    if lean:
        out.append(f'<p style="font-family:{SANS};font-size:13px;margin:0 0 22px;">{a("Every Lean project Paperlane has built &rarr;", base + "/lean.html", f"color:{MUTED};")}</p>')
    out.append(f'<p style="font-family:{SANS};font-size:14px;color:{INK2};margin:0 0 4px;padding-top:16px;border-top:1px solid {RULE};">'
               f'Reply to this email to tell me what would make it more useful. I read every reply.</p>')
    out.append(f'<p style="font-family:{SERIF};font-style:italic;font-size:15px;color:{INK};margin:0 0 16px;">Pragyaan, who builds Paperlane</p>')
    out.append(f'<p style="font-family:{SANS};font-size:12px;color:{MUTED};margin:0;">Paperlane is a free daily list of new arXiv mathematics papers. {esc(render.ARXIV_THANKS)}</p>')
    return (f'<div style="max-width:600px;margin:0 auto;background:{PAPER};color:{INK};">' + out[0]
            + '<div style="padding:0 24px 28px;">' + "\n".join(out[1:]) + "</div></div>")


def send(subject, body, key, day, send_now=False, html_body=None):
    """Create a Kit broadcast for every subscriber. Without send_now it stays a draft in Kit."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "subject": subject,
        "content": html_body or to_html(body),
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
        return f'<a href="{html.escape(html.unescape(m.group(2)))}">{text}</a>'

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
