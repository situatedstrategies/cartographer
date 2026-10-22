# Cartographer

A map of how you build with coding agents. Cartographer reads the session history your agent already keeps and tells each session back to you as a story in second person: what you did, what happened, what it meant, how you responded, with turning points marked, reusable prompts and coaching. It files the map under the git repo it belongs to and replays the whole build when the project is done.

Works with **Claude Code**, **Codex CLI** and **Cursor**, and with any other agent through a generic transcript adapter. Pure Python 3.9+, no dependencies.

## Install

One line, from [codecartographer.dev](https://codecartographer.dev):

```bash
curl -fsSL https://codecartographer.dev/install.sh | sh     # Mac, Linux
irm https://codecartographer.dev/install.ps1 | iex           # Windows, PowerShell
```

Or from a checkout:

```bash
git clone https://github.com/situatedstrategies/cartographer && cd cartographer
./bin/cartographer install --agent all   # copies itself to ~/.cartographer/app, puts `cartographer` in ~/.local/bin
cartographer config init                  # aptitude profile, feedback, voice, manual/auto (or: cartographer serve --open)
```

Needs Python 3.9 or newer and nothing else. On Windows the command is `python bin\cartographer install …`; hooks are registered as `"python.exe" "…/bin/cartographer" hook claude-code`, so no Unix shell is needed.

`install` puts `/wrap`, `/replay` and `/cartographer-setup` into Claude Code, writes wrap instructions into `~/.codex/AGENTS.md`, and prints the Cursor rule (or writes it with `--project <repo>`). Add `--auto` to wrap sessions when they end: Claude Code gets a `SessionEnd` hook and Cursor a `stop` hook. Codex has no end event, so run `cartographer sweep` on a schedule; the install prints the cron line.

## Use

| In the agent | What happens |
|---|---|
| `/wrap` (Claude Code, Cursor, Codex) | `cartographer wrap` digests the transcript and writes a **brief**: session facts, your aptitude profile, what Cartographer knows about the languages used, a pragmatic reading of every prompt, the mapping rules and the timeline. The agent follows it, writes the recap, and `cartographer save` files it and renders the replay. |
| `/replay <project>` | The story of every wrapped session in the repo, across agents and branches, told one move at a time, plus the playbook. Switch **Story** to **Map** for the trail of the build (it climbs with outcomes that worked, dips with setbacks, and rings achievements in gold), and **Plain** to **Native** for everyday words or the words of the code. Space plays, arrow keys step, the time strip jumps to any minute. |
| `/complete <project>` | Mark a version shipped, partial or abandoned, say what actually happened, and get the **appraisal**: every session's moves judged against the outcome you declared, with evidence, minutes, and the technical implications now living in the result. |
| `/cartographer-setup` | Change the profile, switch manual/auto, or backfill maps of old sessions. |

Session maps are provisional. The source of truth is the outcome you wanted, and it is only known when a version is done, so `cartographer goal "…"` declares what done means, every wrap is judged against it, and `/complete` writes the honest reading at the end. Every move and every appraisal item must cite its evidence in the record (which prompt, which error, which repair, which pause), and `save` rejects praise words.

The dashboard, for anyone who would rather click than type:

```bash
cartographer serve --open      # http://127.0.0.1:8765, this machine only
cartographer open [project]    # open a replay directly (default: the newest)
```

It shows your projects with their maps, recent sessions with a **Map this session** button, the setup form, and Claude Code installation. Every button that changes something carries a per-run token, so a page open in another tab cannot trigger it, and nothing leaves your machine.

From a shell:

```bash
cartographer sessions --all           # every session found, ✓ = wrapped
cartographer wrap --session <id>      # brief for any past session; --run maps it with the agent's headless CLI
cartographer goal "what done means"   # the yardstick for the current version of the repo you are in
cartographer complete --result partial --actual "what happened"   # mark it done, get the appraisal brief; --run appraises headlessly
cartographer save recap.json --check  # validate a recap without storing it
cartographer backfill --cwd <repo>    # briefs for every past session of a repo; --run maps them
cartographer render --project <name> --open
cartographer sweep --dry              # what auto-wrap would pick up
cartographer doctor
```

## How the map is made

```
agent history ──adapter──▶ Session (common events) ──digest──▶ timeline + pragmatics + languages
                                                                      │
config (aptitude, voice, feedback) ───────────────────▶ brief ◀───────┘
                                                          │
                     mapping agent (any) writes recap ◀───┘ ──save──▶ ~/.cartographer/sessions/<repo>/…
                                                                            │
                                                                        replay HTML
```

* **Adapters** (`cartographer/adapters/`) turn each agent's on-disk history into one event stream: prompts, replies, tools, errors, branch changes, notes. Adding an agent is one file.
* **Language layer** (`cartographer/lang.py`) detects languages and frameworks from files edited, code pasted and names used, and reads every prompt for three things: the **act** it performs (build, fix, repair, accept, ask…), what it **anchors** to (paths, symbols, errors, pasted code; specificity 0–3) and its **pragmatics** (imperative or question, hedges, delegation, scope, vague wording). Turn-initial repairs ("no, I meant…") are flagged because they usually mark a dead end. A short standing note per language goes into the brief as a prior; the mapping model's own knowledge applies on top, which is why old sessions can be mapped retrospectively.
* **Config** (`~/.cartographer/config.json`) holds the aptitude profile. New coders get plain-language maps and feedback about what the code did; advanced coders get code-level feedback with files cited. New prompters get concrete rewrites of their real prompts; advanced prompters get prompt-architecture feedback tied to the profile numbers. Exact prompts are kept unless you turn that off. Secrets are redacted before anything is written.
* **Projects are git repos.** The project id is the normalized remote (`github.com/me/app`) so two clones are one project; branches are recorded per session and per step and show up as lanes in the replay.

## Layout

```
cartographer/     package: adapters/, lang, digest, brief, recap, store, render, serve, hooks, autowrap, cli
skills/           Claude Code skills: wrap, replay, complete, cartographer-setup
bin/cartographer  runs the CLI from a checkout
tests/            python3 -m unittest discover -s tests -v
demo/             a wrapped session and its replay
site/             codecartographer.dev pieces that are not the CLI (the mail worker)
```

Everything lives under `~/.cartographer` (override with `CARTOGRAPHER_HOME`): `config.json`, `projects.json` (projects and their versions: desired outcome, result, what happened), `sessions/<project>/<date>_<agent>_<id>.json` (one map per session) and `sessions/<project>/appraisal_<version>.json`, `replays/`, `briefs/`, `digests/`. Which sessions are wrapped is read from the recap file names, so there is nothing else to keep in sync.

## Status

Prototype. Claude Code's format is verified against real sessions; the Codex CLI and Cursor adapters follow their documented on-disk layouts and are covered by synthetic fixtures, so expect to adjust them when those tools change. Headless runners (`claude -p`, `codex exec`, `cursor-agent -p`) are configurable under `agents.<name>.headless`.
