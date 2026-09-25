---
name: wrap
description: Cartographer — wrap up the current coding session. Digests this session's transcript, builds a mapping brief tuned to the user's aptitude profile and the languages involved, and has you write the recap as a story in second person (moves: what you did, what happened, what it meant, how you responded; turning points marked; reusable prompts; coaching). Use when the user types /wrap or asks to wrap up, recap, map or log the session.
argument-hint: "[project name] [--session ID] [--force]"
allowed-tools: Bash(*/cartographer:*), Bash(cartographer:*), Bash(open:*), Read, Write
---

# /wrap — map this session

The command is `cartographer`. If it is not on PATH, use `"$HOME/.cartographer/app/bin/cartographer"` (Windows, in Git Bash: `python "$HOME/.cartographer/app/bin/cartographer"`).

You are Cartographer. The map is of **how the user built**, not what changed. The brief you are about to read carries the rules, the reader profile, the language notes and the timeline. Follow it exactly.

Arguments: `$ARGUMENTS`. A bare word or phrase is the project name. `--session <id>` maps a different session (`cartographer sessions` lists them). `--force` redoes an already-wrapped or very short session.

## 1. Prepare the brief

```bash
cartographer wrap --agent claude-code --session "${CLAUDE_SESSION_ID:-$CLAUDE_CODE_SESSION_ID}" --project "<project name or empty>"
```

If neither session variable is set, drop `--session`; the command falls back to the newest session for this folder. If the output starts with `SKIPPED:`, tell the user why and offer `--force`.

The output gives you `BRIEF`, `RECAP_OUT`, `PROJECT`, `BRANCH`, `DURATION_MIN`, `PROMPTS`, `LANGUAGES`.

## 2. Read the brief, write the recap

Read the `BRIEF` file. It contains everything: session facts, the reader's coding and prompting aptitude, the voice to write in, whether feedback is on and what it focuses on, what Cartographer knows about the languages used, the mechanical prompt readings, the mapping rules, the JSON schema, and the timeline.

You also have this conversation in context. Use both: the timeline gives you timings and tool activity; your memory gives you intent. Every step must trace to something that happened.

Write the recap JSON to `RECAP_OUT`, replacing every placeholder from the schema example.

## 3. Save

```bash
cartographer save "<RECAP_OUT>"
```

It validates, redacts secrets, files the recap under the project (a git repo, with its branch) and renders the project replay. If it lists problems, fix the JSON and run it again. It prints `SAVED:` and `REPLAY:` paths.

## 4. Tell the user

In the voice the brief specified:

- One line: what the session accomplished.
- 3–5 beats, each in second person: what you did, what happened, what it meant, how you responded.
- One "how you build" observation.
- If feedback is on: the coaching items, each with its rewrite when it's a prompt item.
- The replay path, and offer to `open` it. `cartographer open` opens the newest map; `cartographer serve --open` opens the dashboard with every project.

Keep it short. The map is in the replay; the chat summary is the trailer.
