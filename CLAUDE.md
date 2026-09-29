# CLAUDE.md - Cartographer

Project instructions for Claude Code. Read this in full before any task in
this repository.

## What this is

Cartographer, an open source (MIT) command line tool that reads the session
history a coding agent keeps and turns it into a map of how a project was
built. The CLI lives in `cartographer/` and `bin/`; the skills in `skills/`;
the public site for codecartographer.dev in `site/www/`, deployed as a
Cloudflare Worker with static assets (root directory `site`, build
`sh build.sh`, deploy `npx wrangler deploy`). Pushing to `main` deploys.

## Hard copy rules for the site

- No em dashes and no en dashes in anything new. Grep the diff for U+2014
  and U+2013.
- Claims about Cartographer must match what the code does and what the
  README and `site/www/how-it-works.html` already say. Claims about other
  tools come only from their vendors' own documentation, cited.
- Never commit to main except for a blog release that meets every condition
  below. Every other change goes to a branch.

## The blog on codecartographer.dev

Blog posts are the one kind of change that may be pushed to main without a
per-change go-ahead. Everything in this section is a hard condition on that
permission. `marketing/cartographer-blog-editorial.md` is the companion operating
manual for scheduled blog runs; where the two disagree, this file wins.

### What a blog release may touch

A blog release pushed to main may contain only:

- One new post file under `site/www/blog/` (copy `site/www/blog/_template.html`; never publish the template itself)
- `site/www/blog/index.html` (created from `site/www/blog/_index-template.html` on the first release; the new card goes at the top afterwards)
- One new URL line in `site/www/sitemap.xml`
- The regenerated `site/www/blog/feed.xml`, `site/www/blog/feed.json` and
  `site/www/llms-full.txt`, produced by running `node scripts/build-feed.mjs` and
  `node scripts/build-llms-full.mjs` from the repo root after the sitemap line
  is in (never edited by hand)
- On the first release only: the Blog link in the nav and footer of every page
- The topic-queue edit in `marketing/cartographer-blog-editorial.md`

If the diff touches anything else, even one line, it is not a blog release.
It goes to a branch and waits for the owner's merge like every other change.

### How to write a post

- **Topics.** About the reader's world, not the product. The editorial guide
  lists the pillars. Vary the register: analysis and musings both welcome;
  thin keyword filler is not.
- **Voice.** Every post is bylined exactly "By Team Cartographer", no individual
  names, never "the Cartographer team" or any other form of the name. Never
  first person singular. Warm, plain, direct, contraction-friendly, free of
  jargon and hype.
- **Citations are mandatory and must be REAL, accurate, and live.** Every
  factual or statistical claim is verified during the run by finding the
  source through web search and opening it whenever the network policy
  allows. Never cite from memory, never invent a study, never cite a source
  that did not surface in that run's searches with its exact URL and the
  claimed finding. The wording must state the finding no more strongly, and
  no less precisely, than the source does. Every footnote link must resolve
  at publish time; when a fetch is blocked rather than the page being down,
  confirm the exact URL and the exact claim surfaced together in that run's
  own search results, and say in the release report which method was used
  for each source. If a claim cannot be verified this way, cut the claim.
- **Citation format.** Every cited claim is linked twice. The claim's key
  phrase in the text links directly to the source
  (`<a href="URL" rel="noopener">phrase</a>`), and a numbered superscript
  marker after the sentence points at the Sources list at the end. Markers
  and entries match one to one, and each entry carries the full source name
  and the same working link.
- **Dates.** Dates shown to readers are written in full with the day as an
  ordinal and nothing abbreviated, for example "September 12th 2026".
  Machine dates (JSON-LD, sitemap lastmod) stay YYYY-MM-DD.
- **No em dashes and no en dashes, ever.** Grep the diff for U+2014 and
  U+2013 before release; the count must be zero.
- Nothing about any agent or model is stated unless it comes from its
  vendor's own documentation, cited.

### Revise, then check, then release

Never publish a first draft. Every post gets, in order: a revision pass, an
error check (spelling, grammar, every footnote confirmed, every cited
sentence reread against the source, title and description lengths computed),
and the mechanical checks (dash grep, file-scope check, the rules above).
Only when all three pass may the release be pushed to main. If any check
fails and cannot be fixed within the blog-release file scope, push a branch
instead and report what happened.

The first release creates `site/www/blog/index.html` from `site/www/blog/_index-template.html` and adds the Blog link to the nav and footer of every page; later releases only add a card. The two template files are listed in `site/www/.assetsignore` so they are never deployed.