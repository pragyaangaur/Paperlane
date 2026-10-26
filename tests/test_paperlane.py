"""Offline tests. Run with `python -m unittest` from the project folder."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from paperlane import arxiv, render, signals
from paperlane.categories import math_categories

FIXTURES = Path(__file__).parent / "fixtures"


class RssTest(unittest.TestCase):
    def setUp(self):
        self.day, self.items = arxiv.parse_rss((FIXTURES / "math.rss").read_bytes())

    def test_date_and_types(self):
        self.assertEqual(self.day, date(2026, 10, 23))
        self.assertEqual([i["announce_type"] for i in self.items], ["new", "cross", "replace"])

    def test_ids_and_versions(self):
        self.assertEqual([(i["id"], i["version"]) for i in self.items], [("2610.31212", 1), ("2610.31638", 1), ("math/0601001", 3)])

    def test_fields(self):
        first = self.items[0]
        self.assertEqual(first["authors"], ["Ada Lovelace", "Emmy Noether"])
        self.assertTrue(first["abstract"].startswith("We prove a theorem."))
        self.assertEqual(self.items[1]["categories"], ["cs.CC", "math.CO"])

    def test_empty_feed(self):
        empty = b"<rss version='2.0'><channel><pubDate>Sat, 24 Oct 2026 00:00:00 -0400</pubDate></channel></rss>"
        self.assertEqual(arxiv.parse_rss(empty)[1], [])


class SignalTest(unittest.TestCase):
    def test_links_trimmed(self):
        text = "Code at https://github.com/foo/bar). See (github.com/a/b.git), and http://example.org/x."
        self.assertEqual(signals.find_links(text), ["https://github.com/foo/bar", "https://github.com/a/b.git", "https://example.org/x"])

    def test_github_repo(self):
        self.assertEqual(signals.github_repo("https://github.com/a/b.git"), "a/b")
        self.assertEqual(signals.github_repo("https://github.com/a/b/tree/main/lean"), "a/b")
        self.assertIsNone(signals.github_repo("https://github.com/a"))
        self.assertIsNone(signals.github_repo("https://github.com/orgs/x"))
        self.assertIsNone(signals.github_repo("https://gitlab.com/a/b"))

    def test_lean_mentions(self):
        yes = ["machine-verified in Lean~4.", "A Lean 4 formalization", "uses Mathlib", "formalized in Lean."]
        no = ["a lean proof", "Leanne Smith", "lean manufacturing"]
        for t in yes:
            self.assertTrue(signals.LEAN_RE.search(t), t)
        for t in no:
            self.assertFalse(signals.LEAN_RE.search(t), t)

    def test_compute_without_network(self):
        paper = {"abstract": "See https://github.com/x/y.", "comments": None, "announce_type": "replace", "version": 2}
        s = signals.compute(paper, {}, check_github=False)
        self.assertEqual(s["code_links"], ["https://github.com/x/y"])
        self.assertTrue(s["new_version"])
        self.assertFalse(s["lean_repo"])

    def test_math_categories(self):
        self.assertEqual(math_categories(["cs.IT", "math-ph", "math.CO", "cs.CC", "math.CO"]), ["math.IT", "math.MP", "math.CO"])


def sample_day():
    def paper(aid, kind, cats, links=None, lean=False):
        p = {
            "id": aid, "version": 1, "announce_type": kind, "title": f"Title {aid} with $x^2$",
            "authors": ["A. Author", "B. Author"], "abstract": "An abstract & more.", "comments": None,
            "journal_ref": None, "doi": None, "primary_category": cats[0], "categories": cats,
            "license": None, "published": None, "updated": None,
        }
        p["math_categories"] = math_categories(cats)
        p["links"] = {"abs": f"https://arxiv.org/abs/{aid}v1", "pdf": f"https://arxiv.org/pdf/{aid}v1"}
        p["signals"] = {
            "code_links": links or [], "other_links": [], "mentions_lean": lean, "new_version": kind == "replace",
            "github": [{"repo": "x/y", "status": "ok", "lean": True, "lean_paths": ["lean-toolchain"]}] if lean else [],
            "lean_repo": lean, "journal_ref": False,
        }
        return p

    return {
        "schema": 1, "date": "2026-10-23", "source": "rss", "fetched_at": "2026-10-23T02:05:00Z",
        "papers": [
            paper("2610.00001", "new", ["math.CO"], ["https://github.com/x/y"], lean=True),
            paper("2610.00002", "cross", ["cs.CC", "math.CO"]),
            paper("2610.00003", "replace", ["math.NT"]),
        ],
    }


class RenderTest(unittest.TestCase):
    def test_old_issues_expire(self):
        old = dict(sample_day(), date="2026-07-01", papers=[sample_day()["papers"][0] | {"id": "2607.00001"}])
        with tempfile.TemporaryDirectory() as tmp:
            render.build([sample_day(), old], tmp, "https://example.org/paperlane/")
            out = Path(tmp)
            self.assertFalse((out / "days/2026-07-01.html").exists())
            self.assertFalse((out / "p/2607.00001.html").exists())
            self.assertIn("issue no. 2", (out / "index.html").read_text())

    def test_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            render.build([sample_day()], tmp, "https://example.org/paperlane/")
            out = Path(tmp)
            for name in ["index.html", "today.html", "about.html", "latest.md", "latest.json", "latest-titles.md", "feed.xml", "llms.txt",
                         "archive.html", "days/2026-10-23.html", "latest/math.CO.md", "assets/app.js",
                         "p/2610.00001.md", "p/2610.00001.html", "p/2610.00003.md",
                         "404.html", "sitemap.xml", "assets/og.png"]:
                self.assertTrue((out / name).exists(), name)
            index = (out / "today.html").read_text()
            home = (out / "index.html").read_text()
            self.assertIn('id="finder-q"', home)
            self.assertIn("An abstract &amp; more.", index)
            self.assertIn("Lean project", index)
            self.assertIn('data-cats="math.CO"', index)
            titles = (out / "latest-titles.md").read_text()
            self.assertIn("Lean project: lean-toolchain", titles)
            data = json.loads((out / "latest.json").read_text())
            self.assertEqual(data["papers"][0]["paperlane_url"], "https://example.org/paperlane/p/2610.00001.html")
            single = (out / "p" / "2610.00001.md").read_text()
            self.assertTrue(single.startswith("# Title 2610.00001"))
            self.assertIn("Lean project: lean-toolchain", single)
            feed = (out / "feed.xml").read_text()
            self.assertEqual(feed.count("<item>"), 2)  # new versions stay out of the feed
            self.assertIn("https://example.org/paperlane/latest-titles.md", (out / "llms.txt").read_text())
            self.assertTrue((out / "paper.html").exists())
            self.assertIn('data-md="p/2610.00001.md"', index)
            self.assertIn('name="cat" value="math.CO"', index)

    def test_pages_of(self):
        self.assertEqual(render.pages_of({"comments": "42 pages, 2 figures"}), 42)
        self.assertEqual(render.pages_of({"comments": "12pp"}), 12)
        self.assertIsNone(render.pages_of({"comments": "Comments welcome"}))

    def test_linkify(self):
        html_out = render.linkify("Code at https://github.com/x/y. <b>")
        self.assertIn('<a href="https://github.com/x/y" target="_blank" rel="nofollow noopener">https://github.com/x/y</a>.', html_out)
        self.assertIn("&lt;b&gt;", html_out)

    def test_tex_text(self):
        self.assertEqual(render.tex_text("Lax--Wendroff and A---B <i>"), "Lax\u2013Wendroff and A\u2014B &lt;i&gt;")
        self.assertEqual(render.tex_text("x -- y"), "x -- y")


if __name__ == "__main__":
    unittest.main()
