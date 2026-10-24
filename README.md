# Paperlane

Paperlane is a free daily feed of new arXiv mathematics papers, built for people and for the AI agents they read with. Every day it publishes the night's announcement as a browsable website, a Markdown page, a JSON file, an RSS feed and an `llms.txt` index. Titles, authors, abstracts and categories come from arXiv and every entry links back to arXiv for the full text.

Each paper carries signals that plain code can check. Paperlane lists every code link in the abstract or comments and looks inside each linked GitHub repository for a Lean project (a `lakefile` or `lean-toolchain` file). It also notes when the abstract mentions Lean and when an entry is a new version of an older paper. Paperlane never scores papers or authors, so each reader's own assistant does the ranking against that reader's interests.

## Running it

It needs Python 3.10 or later and nothing else.

```bash
python3 -m paperlane fetch
```

This fetches the latest announcement from the arXiv RSS feed, looks up comments in the arXiv API, checks linked repositories and stores the day in `data/days/`. On nights with no announcement it stores nothing. To backfill a day, or to test on a weekend, use `--api-date 2026-10-23`, which approximates that day from submission times and has no new versions.

```bash
python3 -m paperlane build --base-url http://localhost:8000
python3 -m http.server 8000 --directory _site
```

This renders every stored day into `_site/` and serves it locally. The tests run offline with `python3 -m unittest`.

## What the site publishes

| Path | What it is |
| --- | --- |
| `index.html` | The latest day, with subfield filters, code and Lean filters, a search box and the paste-in prompt |
| `latest-titles.md` | One line per paper with its id, categories, signals, title and authors, which is the place for an agent to start |
| `latest.md` and `latest.json` | The latest day with abstracts |
| `latest/<category>.md` | The latest day for one subfield, for example `latest/math.CO.md` |
| `p/<id>.md` and `p/<id>.html` | One page per paper, which is the link to share. Old ids such as `math/0601001` use a hyphen in place of the slash |
| `days/<date>.html`, `.md`, `.json` | Every past day |
| `feed.xml` | RSS of the latest day's new papers and cross-lists |
| `llms.txt` | An index for agents |

## Deployment

`.github/workflows/daily.yml` runs at 06:00 UTC every day. It fetches the day, commits it to `data/days/`, builds the site and deploys it to GitHub Pages. arXiv announces at 20:00 US Eastern time but rebuilds its RSS feed at midnight Eastern, which is 05:00 UTC in winter, so the job waits until after that. The repository needs Pages set to deploy from GitHub Actions.

Thank you to arXiv for use of its open access interoperability.
