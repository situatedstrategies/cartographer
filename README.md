# Cartographer

A map of how you build with coding agents. Cartographer reads the session history your agent already keeps, maps each session (phases, turning points, dead ends, fixes, reusable prompts, coaching), files it under the git repo it belongs to, and replays the whole build when the project is done.

Works with **Claude Code**, **Codex CLI** and **Cursor** out of the box, and with any other agent through a generic transcript adapter. No dependencies beyond Python 3.9+.

## Install

```bash
git clone <this repo> cartographer && cd cartographer
./bin/cartographer install --agent all        # copies itself to ~/.cartographer/app, links ~/.local/bin/cartographer
cartographer config init                       # aptitude profile, feedback, voice, manual/auto
```

`install` puts `/wrap`, `/replay` and `/cartographer-setup` into Claude Code, writes wrap instructions into `~/.codex/AGENTS.md`, and prints the Cursor rule (or writes it with `--project <repo>`). Add `--auto` to wrap sessions automatically when they end (Claude Code `SessionEnd` hook, Cursor `stop` hook; Codex gets a `notify` hook plus a periodic `cartographer sweep`, which `--launchd` schedules on macOS).

## Use

| In the agent | What happens |
|---|---|
| `/wrap` (Claude Code) · "wrap up this session" (Codex, Cursor) | `cartographer wrap` digests the transcript and writes a **brief**: session facts, your aptitude profile, what Cartographer knows about the languages used, the mapping rules, and the timeline with a pragmatic reading of every prompt. The agent follows it, writes the recap, and `cartographer save` files it and renders the replay. |
| `/replay <project>` | One animated map of every wrapped session in the repo, across agents and branches, plus the playbook. |
| `/cartographer-setup` | Change the profile, switch manual/auto, or backfill maps of old sessions. |

From a shell:

```bash
cartographer sessions --all          # every session found, ✓ = wrapped
cartographer wrap --session <id>     # brief for any past session (retrospective maps)
cartographer backfill --cwd <repo>   # briefs for every past session of a repo; --run maps them headlessly
cartographer render --project <name> --open
cartographer sweep                   # auto-wrap ended/idle sessions
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

* **Adapters** (`cartographer/adapters/`) turn each agent's on-disk history into the same event stream: prompts, replies, tools, errors, branch changes. Adding an agent is one file.
* **Language layer** (`cartographer/lang.py`) detects languages and frameworks from files, pasted code and names, reads every prompt for act, anchoring and pragmatics, and carries standing notes on how prompts about each language behave. Those notes go into the brief as priors; the mapping model's own knowledge applies on top, which is why old sessions can be mapped retrospectively.
* **Config** (`~/.cartographer/config.json`) holds the aptitude profile. New coders get plain-language maps and feedback about what the code did; advanced coders get code-level feedback with files cited. New prompters get concrete rewrites of their real prompts; advanced prompters get prompt-architecture feedback tied to the profile numbers. Exact prompts are kept unless you turn that off. Secrets are redacted before anything is written.
* **Projects are git repos.** The project id is the normalized remote (`github.com/me/app`) so two clones are one project; branches are recorded per session and per step and show up as lanes in the replay.

## Layout

```
cartographer/            package (adapters/, lang, digest, brief, recap, store, render, hooks, autowrap, cli)
skills/                  Claude Code skills: wrap, replay, cartographer-setup, references/
bin/cartographer         runs the CLI from a checkout
tests/                   python3 -m unittest discover -s tests -v
demo/                    a wrapped session and its replay
```

## Status

Prototype. Claude Code's format is verified against real sessions; Codex CLI and Cursor adapters follow their documented on-disk layouts and are covered by synthetic fixtures, so expect to adjust them when those tools change. Headless runners (`claude -p`, `codex exec`, `cursor-agent -p`) are configurable under `agents.<name>.headless`.
