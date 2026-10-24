"""Fetch the day's mathematics papers from arXiv.

The daily list comes from the arXiv RSS feed, which is exactly what arXiv announced
that night and says whether each entry is new, a cross-list or a replacement. The
RSS has no comments field, so every entry is then looked up in the arXiv API.

For backfill and testing on days with no announcement there is a second path that
asks the API for every math paper submitted in a 24 hour window. That window only
approximates an announcement and has no replacements, so days built that way are
marked with source "api-window".
"""

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import USER_AGENT
from .categories import math_categories

RSS_URL = "https://rss.arxiv.org/rss/math"
API_URL = "https://export.arxiv.org/api/query"
API_PAUSE = 3.1  # arXiv asks for at most one API request every three seconds
ID_BATCH = 100

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

ID_RE = re.compile(r"(\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[A-Z]{2})?/\d{7})(?:v(\d+))?")


def http_get(url, tries=4, pause=5.0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == tries - 1:
                raise
            wait = pause * (attempt + 1)
            print(f"  fetch failed ({e}), retrying in {wait:.0f}s")
            time.sleep(wait)


def split_id(text):
    m = ID_RE.search(text or "")
    if not m:
        return None, None
    return m.group(1), int(m.group(2)) if m.group(2) else None


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


# RSS


def parse_rss(xml_bytes):
    """Return (announcement date or None, list of entries) from the arXiv RSS feed."""
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    day = None
    pub = channel.findtext("pubDate") if channel is not None else None
    if pub:
        day = parsedate_to_datetime(pub).date()
    items = []
    for item in root.iter("item"):
        aid, version = split_id(item.findtext("guid") or item.findtext("link"))
        if not aid:
            continue
        desc = item.findtext("description") or ""
        kind = item.findtext("arxiv:announce_type", namespaces=NS)
        if not kind:
            m = re.search(r"Announce Type:\s*(\S+)", desc)
            kind = m.group(1) if m else "new"
        abstract = desc.split("Abstract:", 1)[1] if "Abstract:" in desc else ""
        creators = item.findtext("dc:creator", namespaces=NS) or ""
        items.append(
            {
                "id": aid,
                "version": version,
                "announce_type": kind.strip(),
                "license": item.findtext("dc:rights", namespaces=NS),
                "title": clean(item.findtext("title")),
                "abstract": clean(abstract),
                "authors": [a.strip() for a in creators.split(",") if a.strip()],
                "categories": [c.text.strip() for c in item.findall("category") if c.text],
            }
        )
    return day, items


# API


def parse_api(xml_bytes):
    root = ET.fromstring(xml_bytes)
    total = root.findtext("opensearch:totalResults", namespaces=NS)
    entries = []
    for e in root.findall("atom:entry", NS):
        aid, version = split_id(e.findtext("atom:id", namespaces=NS))
        title = clean(e.findtext("atom:title", namespaces=NS))
        if not aid or title == "Error":
            continue
        primary = e.find("arxiv:primary_category", NS)
        entries.append(
            {
                "id": aid,
                "version": version or 1,
                "title": title,
                "authors": [clean(a.findtext("atom:name", namespaces=NS)) for a in e.findall("atom:author", NS)],
                "abstract": clean(e.findtext("atom:summary", namespaces=NS)),
                "comments": clean(e.findtext("arxiv:comment", namespaces=NS)) or None,
                "journal_ref": clean(e.findtext("arxiv:journal_ref", namespaces=NS)) or None,
                "doi": clean(e.findtext("arxiv:doi", namespaces=NS)) or None,
                "primary_category": primary.get("term") if primary is not None else None,
                "categories": [c.get("term") for c in e.findall("atom:category", NS)],
                "published": e.findtext("atom:published", namespaces=NS),
                "updated": e.findtext("atom:updated", namespaces=NS),
            }
        )
    return int(total or 0), entries


def api_by_ids(ids):
    out = {}
    for i in range(0, len(ids), ID_BATCH):
        batch = ids[i : i + ID_BATCH]
        url = API_URL + "?" + urllib.parse.urlencode({"id_list": ",".join(batch), "max_results": len(batch)})
        _, entries = parse_api(http_get(url))
        out.update({e["id"]: e for e in entries})
        print(f"  API details {min(i + ID_BATCH, len(ids))}/{len(ids)}")
        time.sleep(API_PAUSE)
    return out


def api_window(start, end, page=500):
    """Every math paper first submitted between two UTC datetimes."""
    fmt = "%Y%m%d%H%M"
    query = f"cat:math.* AND submittedDate:[{start.strftime(fmt)} TO {end.strftime(fmt)}]"
    out, offset, total = [], 0, None
    while total is None or offset < total:
        params = {
            "search_query": query,
            "start": offset,
            "max_results": page,
            "sortBy": "submittedDate",
            "sortOrder": "ascending",
        }
        total, entries = parse_api(http_get(API_URL + "?" + urllib.parse.urlencode(params)))
        out.extend(entries)
        offset += page
        print(f"  API window {min(offset, total)}/{total}")
        time.sleep(API_PAUSE)
        if not entries:
            break
    return out


# Days


def _links(aid, version):
    v = f"v{version}" if version else ""
    return {"abs": f"https://arxiv.org/abs/{aid}{v}", "pdf": f"https://arxiv.org/pdf/{aid}{v}"}


def _paper(base, extra, kind):
    p = {
        "id": base["id"],
        "version": base.get("version") or 1,
        "announce_type": kind,
        "title": base["title"],
        "authors": base["authors"],
        "abstract": base["abstract"],
        "comments": base.get("comments"),
        "journal_ref": base.get("journal_ref"),
        "doi": base.get("doi"),
        "primary_category": base.get("primary_category") or (base["categories"] or [None])[0],
        "categories": base["categories"],
        "license": extra.get("license"),
        "published": base.get("published"),
        "updated": base.get("updated"),
    }
    p["math_categories"] = math_categories([p["primary_category"]] + p["categories"])
    p["links"] = _links(p["id"], p["version"])
    return p


def fetch_rss_day():
    """The night's announcement, or None when arXiv announced nothing."""
    day, items = parse_rss(http_get(RSS_URL))
    print(f"RSS: {len(items)} entries, announced {day}")
    if not items:
        return None
    details = api_by_ids([i["id"] for i in items])
    papers = []
    for item in items:
        api = details.get(item["id"])
        if api is None:
            print(f"  {item['id']} missing from API, using RSS fields")
            api = dict(item, primary_category=None)
        papers.append(_paper(api, item, item["announce_type"]))
    return {"date": day.isoformat(), "source": "rss", "papers": papers}


def fetch_api_day(day):
    """Approximate the announcement on `day` from submission times (no replacements)."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    # arXiv's daily cutoff is 14:00 US Eastern; 18:00 UTC is close enough for a backfill.
    end = datetime(day.year, day.month, day.day, 18, tzinfo=timezone.utc) - timedelta(days=1)
    while end.weekday() >= 5:  # nothing is cut off over the weekend
        end -= timedelta(days=1)
    start = end - timedelta(days=1)
    while start.weekday() >= 5:
        start -= timedelta(days=1)
    print(f"API window {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC")
    papers = []
    for e in api_window(start, end):
        kind = "new" if (e["primary_category"] or "").startswith("math") else "cross"
        papers.append(_paper(e, {}, kind))
    return {"date": day.isoformat(), "source": "api-window", "papers": papers}
