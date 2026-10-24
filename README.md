<p align="center">
  <img src="docs/banner.svg" alt="Paperlane. The day's mathematics, read in a minute." width="100%">
</p>

<p align="center">
  <a href="https://pragyaangaur.github.io/Paperlane/"><img alt="Live site" src="https://img.shields.io/badge/live-pragyaangaur.github.io%2FPaperlane-c8f53c?style=flat-square&labelColor=111210"></a>
  <a href="https://github.com/pragyaangaur/Paperlane/actions/workflows/daily.yml"><img alt="Daily issue" src="https://img.shields.io/github/actions/workflow/status/pragyaangaur/Paperlane/daily.yml?style=flat-square&label=daily%20issue&labelColor=111210"></a>
  <img alt="Updated every weekday at 06:00 UTC" src="https://img.shields.io/badge/updated-weekdays%2006%3A00%20UTC-eceee8?style=flat-square&labelColor=111210">
  <img alt="No cookies" src="https://img.shields.io/badge/cookies-none-eceee8?style=flat-square&labelColor=111210">
</p>

<p align="center">
  <a href="https://pragyaangaur.github.io/Paperlane/"><b>Read today's issue</b></a>
  &nbsp;·&nbsp;
  <a href="https://pragyaangaur.github.io/Paperlane/#lane">Set up your lane</a>
  &nbsp;·&nbsp;
  <a href="https://pragyaangaur.github.io/Paperlane/llms.txt">llms.txt</a>
  &nbsp;·&nbsp;
  <a href="https://pragyaangaur.github.io/Paperlane/about.html">About</a>
</p>

Every weekday a few hundred new mathematics papers come out. One night of them is about 57,000 words of abstracts, the length of a short novel, and almost nobody sees it happen. Paperlane turns each night into one short issue that you can skim in a minute and your AI assistant can read in seconds.

If you do research, you pick your fields and say what you work on, and the papers closest to your work come first. If you are simply curious, you paste one prompt into the AI you already pay for, and it tells you what mathematicians found last night in plain words.

Paperlane is free, needs no account and sets no cookies.

<p align="center">
  <img src="docs/home.png" alt="The Paperlane home page with today's issue, the lane builder and a contents card" width="92%">
</p>

## Start in thirty seconds

1. Open [Paperlane](https://pragyaangaur.github.io/Paperlane/) and tick the fields you follow under **Make it your lane**.
2. Type a few phrases about your work, such as `graph colouring, random walks`.
3. Press **Open my lane**. Your papers rise to the top, and each one shows the words that matched.

Paperlane remembers your fields and interests in your own browser. A lane link carries its settings, so you can bookmark it or send it to a colleague.

<p align="center">
  <img src="docs/lane.png" alt="An issue ranked for graph colouring and random walks, with matched words highlighted under each paper" width="92%">
</p>

## What you can do

- **Skim by field.** Papers are grouped under their main field, and each field shows its first three papers until you ask for the rest. A row of field links at the top jumps straight to the one you want.
- **Rank for yourself.** The **for me** order ranks the whole issue against your interests in your browser.
- **Filter fast.** One search box covers titles, authors and abstracts. The **Code** and **Lean** buttons keep only papers that link to code or to a Lean formalisation.
- **Open any paper.** Paste an arXiv link or id into the box in the header. Papers from any issue open on their own page, and older papers are looked up for you.
- **Take the Markdown.** Every paper has a Markdown version one click away, ready for a chat window or your notes.

## How the order works

The page always says which order is in use, so nothing about the ranking is hidden.

| Order | What it does |
| --- | --- |
| **by field** | Groups papers under their main field, largest first, with your own fields on top. Inside a field, papers keep the order in which they were submitted. |
| **for me** | Ranks papers against your interests with BM25, the standard formula behind most search engines. Titles count twice, exact phrases get a bonus, and British and American spellings match each other. It runs in your browser and your interests are never sent anywhere. |
| **newest** | Puts the latest submissions first. |
| **shortest** | Sorts by the page count that the authors give. |

Paperlane never ranks a paper by who wrote it.

## Not a mathematician?

Paste this into ChatGPT, Claude, Gemini or any assistant that can open web pages:

> Read https://pragyaangaur.github.io/Paperlane/latest-titles.md, the list of new maths papers from the latest Paperlane issue. Pick the two results a curious person with no maths degree would find most surprising, read their abstracts in https://pragyaangaur.github.io/Paperlane/latest.md, and explain each one in plain words with an everyday example.

## Get a briefing every morning

Many assistants can now run scheduled routines. Open [ask-ai in routine mode](https://pragyaangaur.github.io/Paperlane/ask.html?mode=routine), pick a time and type what you work on, and Paperlane writes a prompt that sets up a routine for every weekday. Each run reads the new issue and sends you the three papers worth your time. On days with no new issue it says so in one line. The page shows when the new issue arrives in your own timezone, so you can pick a time after it.

## Why not just ask your AI to read arXiv?

- **A night of maths is a short novel.** Paperlane reads it once and hands your assistant an index of about 7,500 words, so the answer is fast and cheap.
- **Some answers need real work.** Checking every linked repository for a Lean project takes real requests, and compiling the proofs (coming next) takes real computing time. Paperlane does this once, for everyone.
- **Nothing is made up.** Every tag is a plain check that anyone can repeat, so an assistant reading Paperlane cannot be fooled into claiming a proof that does not exist.
- **It remembers.** Every issue stays in the archive, so you can look back across weeks and see when a paper was revised.

## For your AI agent

Open [**ask-ai**](https://pragyaangaur.github.io/Paperlane/ask.html) to build a prompt and send it to ChatGPT, Claude or Perplexity in one click, or write your own:

> Read https://pragyaangaur.github.io/Paperlane/latest-titles.md, Paperlane's index of today's new maths papers. My interests are extremal graph theory and polyominoes. Pick the candidates that fit, read their abstracts in https://pragyaangaur.github.io/Paperlane/latest.md, and tell me which three papers I should read and why.

Tools can fetch the same files directly:

```bash
curl -s https://pragyaangaur.github.io/Paperlane/latest-titles.md | head
```

| File | What it holds |
| --- | --- |
| [`llms.txt`](https://pragyaangaur.github.io/Paperlane/llms.txt) | A guide to every file below, written for language models |
| [`latest-titles.md`](https://pragyaangaur.github.io/Paperlane/latest-titles.md) | One line per paper with its id, fields, tags, title and authors |
| [`latest.md`](https://pragyaangaur.github.io/Paperlane/latest.md) | The whole issue with abstracts |
| [`latest.json`](https://pragyaangaur.github.io/Paperlane/latest.json) | The whole issue with every field |
| `latest/<field>.md` | One field of the issue, for example [`latest/math.CO.md`](https://pragyaangaur.github.io/Paperlane/latest/math.CO.md) |
| `p/<arXiv id>.md` | One paper, for example [`p/2610.30655.md`](https://pragyaangaur.github.io/Paperlane/p/2610.30655.md) |
| [`feed.xml`](https://pragyaangaur.github.io/Paperlane/feed.xml) | RSS for your feed reader |

## How it works

```mermaid
flowchart LR
  A["arXiv announces<br/>new maths papers"] --> B["Daily job<br/>06:00 UTC"]
  B --> C["Checks<br/>code links, Lean projects,<br/>revised versions"]
  C --> D["Issue<br/>web page, Markdown,<br/>JSON, RSS, llms.txt"]
  D --> E["You"]
  D --> F["Your AI agent"]
```

A scheduled job collects the night's announcement, looks up each paper's details, and checks every linked GitHub repository for a Lean project. It then publishes the issue in every format at once. Every tag comes from a simple check that anyone can repeat, and no language model decides anything about a paper.

## What the tags mean

| Tag | Meaning |
| --- | --- |
| `∎ lean` | A linked GitHub repository contains a Lean project (`lean-toolchain` or a `lakefile`) |
| `□ lean` | The paper says it is formalised in Lean, but no repository was found |
| `code` | The abstract or comments link to code on GitHub, GitLab or a similar host |
| `via cs.CC` | A paper from another subject that its authors also listed under mathematics |
| `v2` | A revised version of an older paper |

<table>
  <tr>
    <td width="70%"><img src="docs/paper.png" alt="A single paper page set like the first page of a LaTeX preprint, with its Lean project highlighted"></td>
    <td width="30%"><img src="docs/phone.png" alt="Paperlane on a phone"></td>
  </tr>
</table>

## Privacy

Paperlane counts visits with [GoatCounter](https://www.goatcounter.com), which sets no cookies and stores no personal data. It also counts a few anonymous events, such as a prompt being copied, to learn which features people use. Your fields and interests stay in your browser.

## What comes next

- A check that linked Lean projects actually compile, so the Lean tag can mean a verified proof.
- An optional email digest of your lane.
- A direct connection for AI assistants, so an agent can ask Paperlane for today's papers in your fields.

## Feedback

Paperlane is new and changes quickly. If something feels wrong or you want a feature, please [open an issue](https://github.com/pragyaangaur/Paperlane/issues).

Paper details come from arXiv. Thank you to arXiv for use of its open access interoperability.
