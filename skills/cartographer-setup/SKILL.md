---
name: cartographer-setup
description: Configure Cartographer — aptitude profile (coding and prompting level), feedback focus, map voice (plain or technical), manual vs automatic wrap, exact-prompt retention, and retrospective backfill of past sessions. Use when the user asks to set up, configure or tune Cartographer, or wants maps of old sessions.
argument-hint: "[key value] | backfill"
allowed-tools: Bash(*/cartographer:*), Bash(cartographer:*), Read
---

# /cartographer-setup

`$ARGUMENTS` may be a `key value` pair, `backfill`, or empty.

The command is `"${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}"`.

## Empty: walk through the profile

Ask these one at a time, in plain language, then set them with `config set`:

| Question | Key | Values |
|---|---|---|
| How comfortable are you reading and writing code? | `profile.coding` | new · intermediate · advanced |
| How experienced are you at prompting coding agents? | `profile.prompting` | new · intermediate · advanced |
| Should feedback focus on your prompts, the code the agent wrote, or both? (auto picks from the two answers above) | `feedback.focus` | prompts · code · both · auto |
| Should the map speak in everyday words, code terms, or offer a toggle? | `voice` | plain · technical · both · auto |
| Wrap sessions yourself with /wrap, or automatically when a session ends? | `wrap.mode` | manual · auto |
| Keep your exact prompt wording in recaps? | `privacy.keep_exact_prompts` | true · false |

What the levels do: **new** coders get plain-language maps and feedback that explains what the code did and one thing to check next time; **advanced** coders get code-level feedback (implicit architecture decisions, risky patterns, missing tests) with files cited. **new** prompters get encouraging, concrete rewrites of their real prompts; **advanced** prompters get prompt-architecture feedback (context loading, constraints, acceptance criteria, delegation boundaries) tied to the prompting-profile numbers.

If they switch to `auto`, run `install --agent claude-code --auto` so the SessionEnd hook is added, and mention that Codex and Cursor need `install --agent codex --auto` / `install --agent cursor --auto --project <repo>` plus a periodic `sweep` (`install --launchd` on macOS).

Finish with `config show` and read back the `effective` line in one sentence.

## `key value`: set one thing

```bash
"${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}" config set <key> <value>
```

## `backfill`: retrospective maps

```bash
"${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}" sessions --all --limit 30
```

Show the list, ask which folder or sessions to map. Then for the chosen folder:

```bash
"${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}" backfill --cwd "<folder>"
```

It prepares one brief per past session and prints their paths. Map them one at a time: read the brief, write the recap to its `RECAP_OUT`, run `save`. For a long backlog, offer `backfill --run`, which uses `claude -p` headlessly and takes a few minutes per session.
