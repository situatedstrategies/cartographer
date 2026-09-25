---
name: replay
description: Cartographer — replay a whole project. Stitches every wrapped session of a repo (from any agent, across branches) into one animated map plus a playbook of reusable prompts, patterns, time sinks and coaching. Use when the user types /replay, finishes a project, or asks to see how they built something.
argument-hint: "[project name]"
allowed-tools: Bash(*/cartographer:*), Bash(cartographer:*), Bash(open:*), Read
---

# /replay — watch the build

Project from the user: `$ARGUMENTS`.

1. If no project was given, list them and ask which (or pick the only one):
   ```bash
   "${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}" projects
   ```
2. Render the replay:
   ```bash
   "${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}" render --project "<project>"
   ```
3. Read the recaps under `~/.cartographer/sessions/<slug>/` and tell the story of the build in 5–8 lines: how it started, the turning points, the biggest dead end, which branches carried which work, and what repeats across sessions (patterns that show up more than once). Use the voice the user configured (`cartographer config show` → `effective.voice`).
4. Offer to `open` the replay. Inside it, **Replay the build** draws the map step by step across sessions; the branch filter and the plain/technical toggle are in the controls row.
