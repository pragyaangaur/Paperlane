# Paperlane

**New arXiv maths papers every day, made for you and your AI agent.**

### [Open Paperlane →](https://pragyaangaur.github.io/Paperlane/)

arXiv posts a few hundred new mathematics papers every weekday, and the listing is hard to skim. Paperlane puts each day's papers on one clean page that you can filter by subfield in a second. Every paper is also published as plain Markdown, so your AI assistant can read the whole day and pick out what matters to you. It is free and needs no account.

## What you can do

- **Skim the day.** Each paper shows its title, authors, subfields and the first lines of its abstract. Maths in titles and abstracts is rendered properly.
- **Filter to your field.** Tick one or more subfields in the sidebar, or type a word, an author or an arXiv id. A filtered view has its own URL, so you can bookmark it or send it to a colleague.
- **Find papers with code or Lean.** Paperlane marks papers that link to code. When the link is a GitHub repository with a Lean project inside, the paper gets a green **Lean project** tag.
- **Open any arXiv paper.** Paste an arXiv link or id into the box at the top. Papers from any day on Paperlane open on their own page, and other papers are fetched for you.
- **Read the Markdown.** The **Markdown** button on every paper shows a clean Markdown version right under it, ready to copy into a chat or your notes.
- **Read it your way.** Pick a light or a dark theme, and read on your phone if you like.

## Let your AI pick your papers

Click **Ask your AI** on the site and type what you work on. Paperlane gives you a prompt like this one to paste into any assistant that can open web pages:

> Read https://pragyaangaur.github.io/Paperlane/latest-titles.md, Paperlane's index of today's new arXiv mathematics papers. My interests are extremal graph theory and polyominoes. Pick the candidates that fit, read their abstracts, and tell me which three papers I should read and why.

Paperlane never ranks papers or scores authors. Your own assistant ranks the day against your own interests, which keeps the feed fair to every author.

If you build agents or tools, these files are made for them:

| File | What it holds |
| --- | --- |
| [`llms.txt`](https://pragyaangaur.github.io/Paperlane/llms.txt) | A guide to everything below, written for language models |
| [`latest-titles.md`](https://pragyaangaur.github.io/Paperlane/latest-titles.md) | One line per paper with its id, subfields, signals, title and authors |
| [`latest.md`](https://pragyaangaur.github.io/Paperlane/latest.md) | The whole day with abstracts |
| [`latest.json`](https://pragyaangaur.github.io/Paperlane/latest.json) | The whole day with every field |
| `latest/<subfield>.md` | One subfield of the day, for example [`latest/math.CO.md`](https://pragyaangaur.github.io/Paperlane/latest/math.CO.md) |
| `p/<arXiv id>.md` | One paper, for example [`p/2610.30655.md`](https://pragyaangaur.github.io/Paperlane/p/2610.30655.md) |
| [`feed.xml`](https://pragyaangaur.github.io/Paperlane/feed.xml) | An RSS feed for your feed reader |

## What the tags mean

Every tag on a paper comes from a simple check that anyone can repeat. No language model is involved in any of them.

| Tag | Meaning |
| --- | --- |
| **code** | The abstract or the comments link to GitHub, GitLab, Codeberg, Bitbucket, SourceHut or Hugging Face |
| **Lean project** | A linked GitHub repository contains a `lean-toolchain` or `lakefile` file |
| **mentions Lean** | The abstract or the comments say the work is formalised in Lean, but no Lean repository was found |
| **v2, v3 …** | The entry is a new version of an older paper |
| **published** | The paper has a journal reference |

The Lean project tag only shows that the repository holds a Lean project. A check that the proof actually compiles is planned.

## When it updates

arXiv announces new papers at 20:00 US Eastern time from Sunday to Thursday. Paperlane picks them up at 06:00 UTC the next morning, so a new day appears from Monday to Friday. Every page shows when it was built, and every past day stays in the [archive](https://pragyaangaur.github.io/Paperlane/archive.html).

## Where the data comes from

Titles, authors, abstracts and categories come from arXiv. Paperlane keeps no copy of the full text, and every entry links to arXiv for the PDF. Papers that Paperlane has not listed yet are looked up through Semantic Scholar or OpenAlex when you open them.

Thank you to arXiv for use of its open access interoperability.

## Feedback

Paperlane is new and still growing. If something is wrong or annoying, or you want a feature, please [open an issue](https://github.com/pragyaangaur/Paperlane/issues).
