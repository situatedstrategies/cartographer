# Cartographer blog: editorial guide for automated posts

This file is the operating manual for the scheduled blog-writing runs on
codecartographer.dev. Every run must read this file AND `CLAUDE.md` in full before writing a
word. `CLAUDE.md` always wins on any conflict, and its blog section governs
what a blog release may touch and when it may go to main.

## Cadence and publishing flow

- One post per run, one run every other day.
- Each run branches from the latest `origin/main` and writes exactly one post.
- When the run's diff touches only the blog-release files listed in
  `CLAUDE.md` AND every check below passes, push the release to main. That is
  the production deploy; for blog releases it is authorised without asking.
- If any check fails, or the diff grew beyond the blog-release scope, do NOT
  push to main. Push a `claude/blog-post-YYYY-MM-DD` branch instead and report
  what happened.
- Never open a pull request unless asked.

## Author, voice, and register

Every post is signed collectively: byline exactly "By Team Cartographer", no individual
names. Never "the Cartographer team" or any other form of the name. Vary the register across posts rather than settling into one:

- **Analysis.** A research finding, a documented pattern, or a piece of
  practical knowledge unpacked carefully in a general, informational voice.
- **Musings.** A looser reflection on how the subject actually feels. First
  person plural (we, our) is welcome. Never first person singular (I, my);
  nothing is attributed to a named individual.

In both registers the voice is warm, plain, direct. Contractions always.
Short sentences over long ones. No hype, no exclamation marks, no listicle
filler, nothing that reads like generic content marketing. No em dashes and
no en dashes anywhere.

- Nothing about Claude Code, Codex, Cursor or any other agent is stated unless
  it comes from that vendor's own documentation, cited. No speculation about
  how a model works internally.

The posts are about the reader's world, not about the product. The product
gets one short paragraph per post at most, in plain language, making only
claims the site already makes.

## Topic pillars

1. **Working with coding agents.** How people actually build with agents: prompting, correcting, delegating, when to stop and read.
2. **Session history as a record.** What transcripts and logs hold, what they leave out, reading your own process, learning from the dead ends.
3. **The craft.** Software craft in the agent era: specification, review, honesty about what shipped, judging a build against what was meant.
4. **Research and documentation.** HCI and software engineering research on human-AI collaboration, and official documentation, read carefully.

### Topic queue (take the top one, then delete it from this list)

When the queue runs low, add new topics that fit the pillars and target real
search phrases people use. Never repeat a topic an existing post already
covers.

- Why a correction is the most informative prompt in a session
- Declaring done before you start: goals as a yardstick
- Reading your own dead ends: what abandoned branches teach
- Praise is not evidence: how to appraise an agent's work honestly

## Citations: real, accurate, live sources, footnoted, always

- Every factual or statistical claim must be verified during the run by
  finding the source via web search and opening the page whenever the
  environment's network policy allows fetching it. If fetching is blocked,
  the exact URL and the claimed finding must both have surfaced in that
  run's search results. Never cite from memory, never invent a study, never
  cite anything that didn't surface in that run. If a claim can't be
  verified, cut the claim.
- Prefer primary sources: peer-reviewed studies, professional bodies,
  government data, named surveys, official documentation. Link the study or
  the original publisher, not a blog summarising it.
- **State findings no more strongly, and no less precisely, than the source
  does.** A vague paraphrase that is technically defensible but leaves a
  misleading impression is not acceptable; reread the source's own summary of
  its finding and match it, in plain language.
- **Every footnote link must actually work.** Fetch each one directly when
  the network allows and confirm it still loads and still says what the post
  claims. When a fetch is blocked (not the same as the page being down),
  confirm the exact URL and the exact claim surfaced together in that run's
  own search results, from more than one search if the first result is
  thin, before relying on it. A link nobody has actually opened in that run
  is not yet a verified citation.
- **Citation format.** Every cited claim is linked twice. First, the claim's
  key phrase in the text links directly to the source:
  `<a href="URL" rel="noopener">the phrase that carries the claim</a>`.
  Second, a numbered superscript marker follows the sentence and links to
  the entry in the Sources section at the end of the post. Each entry
  carries the full source name and the same working link. Reuse a number
  when the same source is cited again. Markers and entries must match one
  to one; at least two distinct sources per post. Pick a phrase that names
  the finding or the source, never a bare "here" or "study".
- Claims about the product itself must be substantiated by copy already in
  this repository. A post is about the reader's world, not the product; one
  short paragraph connecting to the product is the most a post carries.

## Reach-out line rotation

Each post ends with a short reach-out line: "Questions, or a topic you'd like
us to dig into next? Reach out any time: [email]. We read everything."

Rotation: `support@codecartographer.dev` → `mapit@codecartographer.dev` → repeat. Determine the next email by checking which one the most
recent post used.

## Post structure

Dates shown to readers are written in full with the day as an ordinal and
nothing abbreviated: "September 12th 2026". JSON-LD dates and the sitemap
lastmod stay YYYY-MM-DD.

Copy `site/www/blog/_template.html` and replace every `{{PLACEHOLDER}}` (`{{DATE}}` is the written-out date, `{{DATE_ISO}}` is YYYY-MM-DD); delete the HTML comments. Create `site/www/blog/index.html` from `_index-template.html` on the first release (replace `{{POSTS}}` with the first card); afterwards add the new card at the top of the list. On the first release only, add `<a href="/blog/">Blog</a>` after Questions in the nav of every page under `site/www/`.

Target length: 700 to 1,000 words of body copy. Head: unique title (70
characters or fewer), meta description (70 to 160 characters), canonical URL,
Open Graph and Twitter tags, BlogPosting JSON-LD with author
`{"@type": "Organization", "name": "Team Cartographer"}` and publisher Situated
Strategies LLC (`@id` https://situatedstrategies.org/#organization).

## Per-run site updates

- Add the new post's card to the TOP of the list on the blog index (newest
  first), matching the existing card markup.
- Add the post's URL to the sitemap with today's date as lastmod.
- Run `node scripts/build-feed.mjs` and `node scripts/build-llms-full.mjs` from
  the repo root and commit the regenerated `site/www/blog/feed.xml`,
  `site/www/blog/feed.json` and `site/www/llms-full.txt` with the post. They
  are read from the post pages and the sitemap, so run them last; never edit
  them by hand.
- Update the topic queue in this file.
- Touch nothing else. The blog-release scope in `CLAUDE.md` is a hard
  boundary: one new file under `site/www/blog/`, `site/www/blog/index.html`, one URL line in `site/www/sitemap.xml`, the regenerated `site/www/blog/feed.xml`, `site/www/blog/feed.json` and `site/www/llms-full.txt`, the nav links on the first release only, and the topic queue in `marketing/cartographer-blog-editorial.md`.

## Revise, then check, then release (all three, in order, every run)

1. **Revision pass.** Re-read the whole draft after writing it. Tighten flow,
   cut filler, confirm the register is consistent, confirm it sounds like the
   site and not like generic content marketing.
2. **Error check.** Spelling and grammar read-through. Reread each cited
   source's own finding side by side with the sentence citing it, and confirm
   the post doesn't overstate, understate, or misleadingly reshape it. Confirm
   every footnote link per the citations rule above. Confirm footnote markers
   and entries match one to one. Compute (don't estimate) title (70 characters
   or fewer) and meta description (70 to 160 characters) lengths.
3. **Mechanical checks, report results explicitly:**
   - [ ] No em dashes (U+2014) or en dashes (U+2013) anywhere in the diff.
   - [ ] Diff touches only the blog-release files listed in CLAUDE.md.
   - [ ] Every factual claim footnoted; every product claim substantiated
         in-repo; no unsubstantiated comparisons to other products.
   - [ ] The site-specific rules in CLAUDE.md (see "Voice and rules" above).

All three pass, and the diff is within the blog-release scope, then push to
main (production). Anything fails, push a `claude/blog-post-YYYY-MM-DD`
branch instead and report why.
