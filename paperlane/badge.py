"""A small SVG badge for each checked Lean repository, for authors to put in their README.

The badge says only what the build check found, in the same words as the site. It is a
static file rebuilt with the site, so it always shows the newest stored result.
"""

from html import escape

# Approximate advance widths of Verdana at 11px, the font most badges use, so the text fits its box.
NARROW = set("fijlrtI.,:;'!|() ")
WIDE = set("mwMW@%")
COLOURS = {
    "builds": ("#c8f53c", "#111210"),
    "sorry": ("#f5d63c", "#111210"),
    "fails": ("#d9534f", "#ffffff"),
    "timeout": ("#8a8a85", "#ffffff"),
    "error": ("#8a8a85", "#ffffff"),
}
LEFT = "Paperlane Lean"


def text_width(text):
    w = 0.0
    for c in text:
        w += 3.6 if c in NARROW else 10.0 if c in WIDE else 7.6 if c.isupper() or c.isdigit() else 6.6
    return round(w)


def value(result):
    s = result["status"]
    if s == "builds":
        return "builds"
    if s == "sorry":
        n = result.get("sorries") or 0
        return f"builds, {n} sorry"
    if s == "fails":
        return "fails"
    if s == "timeout":
        return "timed out"
    return "not checked"


def svg(result):
    right = value(result)
    bg, fg = COLOURS.get(result["status"], COLOURS["error"])
    lw, rw = text_width(LEFT) + 12, text_width(right) + 12
    w = lw + rw
    title = f"{LEFT}: {right}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<clipPath id="r"><rect width="{w}" height="20" rx="3"/></clipPath>
<g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#111210"/><rect x="{lw}" width="{rw}" height="20" fill="{bg}"/></g>
<g font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11" text-anchor="middle">
<text x="{lw / 2}" y="14" fill="#fdfdfc">{escape(LEFT)}</text>
<text x="{lw + rw / 2}" y="14" fill="{fg}">{escape(right)}</text>
</g>
</svg>
"""
