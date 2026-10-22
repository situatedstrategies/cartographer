---
name: cartographer-setup
description: Configure Cartographer — aptitude profile (coding and prompting level), feedback focus, map voice (plain or native), manual vs automatic wrap, exact-prompt retention, and retrospective backfill of past sessions. Use when the user asks to set up, configure or tune Cartographer, or wants maps of old sessions.
argument-hint: "[key value] | backfill"
allowed-tools: Bash(*/cartographer:*), Bash(cartographer:*), Read
---

# /cartographer-setup

The command is `cartographer`. If it is not on PATH, use `"$HOME/.cartographer/app/bin/cartographer"` (Windows, in Git Bash: `python "$HOME/.cartographer/app/bin/cartographer"`).

`$ARGUMENTS` may be a `key value` pair, `backfill`, or empty.

## Empty: walk through the profile

If the user would rather use a form, `cartographer serve --open` opens the local dashboard with the same questions under **Setup**. Otherwise:

Ask these one at a time, in plain language, then set them with `config set`:

| Question | Key | Values |
|---|---|---|
| How comfortable are you reading and writing code? | `profile.coding` | new · intermediate · advanced |
| How experienced are you at prompting coding agents? | `profile.prompting` | new · intermediate · advanced |
| Should feedback focus on your prompts, the code the agent wrote, or both? (auto picks from the two answers above) | `feedback.focus` | prompts · code · both · auto |
| Should the map speak in everyday words, the native words of the code, or offer a toggle? | `voice` | plain · native · both · auto |
| Wrap sessions yourself with /wrap, or automatically when a session ends? | `wrap.mode` | manual · auto |
| Keep your exact prompt wording in recaps? | `privacy.keep_exact_prompts` | true · false |

What the levels do: **new** coders get plain-language maps and feedback that explains what the code did and one thing to check next time; **advanced** coders get code-level feedback (implicit architecture decisions, risky patterns, missing tests) with files cited. **new** prompters get encouraging, concrete rewrites of their real prompts; **advanced** prompters get prompt-architecture feedback (context loading, constraints, acceptance criteria, delegation boundaries) tied to the prompting-profile numbers.

If they switch to `auto`, run `install --agent claude-code --auto` so the SessionEnd hook is added. Cursor needs `install --agent cursor --auto --project <repo>`. `/wrap`, `/replay` and `/complete` are the same three commands in Claude Code, Cursor and Codex; `install --agent all` puts them in all three. Codex has no session-end event, so it needs `install --agent codex --auto` plus `cartographer sweep` on a schedule (the install prints a cron line).

Finish with `config show` and read back the `effective` line in one sentence.

## `key value`: set one thing

```bash
cartographer config set <key> <value>
```

## `backfill`: retrospective maps

```bash
cartographer sessions --all --limit 30
```

Show the list, ask which folder or sessions to map. Then for the chosen folder:

```bash
cartographer backfill --cwd "<folder>"
```

It prepares one brief per past session and prints their paths. Map them one at a time: read the brief, write the recap to its `RECAP_OUT`, run `save`. For a long backlog, offer `backfill --run`, which uses `claude -p` headlessly and takes a few minutes per session.
