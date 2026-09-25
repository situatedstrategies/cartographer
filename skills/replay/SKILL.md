---
name: replay
description: Cartographer — replay a whole project. Stitches every wrapped session of a repo (from any agent, across branches) into one animated map plus a playbook of reusable prompts, patterns, time sinks and coaching. Use when the user types /replay, finishes a project, or asks to see how they built something.
argument-hint: "[project name]"
allowed-tools: Bash(*/cartographer:*), Bash(cartographer:*), Bash(open:*), Read
---

# /replay — watch the build

The command is `cartographer`. If it is not on PATH, use `"$HOME/.cartographer/app/bin/cartographer"` (Windows, in Git Bash: `python "$HOME/.cartographer/app/bin/cartographer"`).

Project from the user: `$ARGUMENTS`.

1. If no project was given, list them and ask which (or pick the only one):
   ```bash
   cartographer projects
   ```
2. Render the replay:
   ```bash
   cartographer render --project "<project>"
   ```
3. Read the recaps under `~/.cartographer/sessions/<slug>/` and tell the story of the build in 5–8 lines, in second person: how it started, the moves that turned it, the biggest setback and how you responded, which branches carried which work, and what repeats across sessions (patterns that show up more than once). Use the voice the user configured (`cartographer config show` → `effective.voice`).
4. Offer to `open` the replay. Inside it, **Replay the build** tells the story one move at a time, chapter by chapter, across sessions; the time strip under the map jumps to any minute; the branch filter, the plain/technical toggle and zoom are in the toolbar. `cartographer serve --open` shows every project on one dashboard.
