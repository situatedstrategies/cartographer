---
name: complete
description: Cartographer — mark a project (or a version of it) complete and write the honest appraisal: the whole build judged against the desired outcome the user declared, using the session maps as evidence. Use when the user says the project or version is done, shipped, finished or abandoned, or asks for the appraisal or post-mortem.
argument-hint: "[project] [--version v1]"
allowed-tools: Bash(*/cartographer:*), Bash(cartographer:*), Bash(open:*), Read, Write
---

# /complete — mark it done, then appraise honestly

The command is `"${CARTOGRAPHER_BIN:-$HOME/.cartographer/app/bin/cartographer}"`. Arguments: `$ARGUMENTS` (a project name, optionally `--version <name>`). With no project, the repo you are in is the project.

## 1. Find the yardstick

Run `cartographer projects`. If the project has no desired outcome declared for the version being closed, ask the user one question: what did "done" mean for this version, in their words? Then set it:

```bash
cartographer goal "<their words>" --project "<project>"
```

## 2. Mark it complete

Ask two things: the result (`shipped`, `partial` or `abandoned`) and, in a sentence, what actually happened. Then:

```bash
cartographer complete --project "<project>" --result <result> --actual "<their sentence>"
```

It prints `BRIEF` and `RECAP_OUT`.

## 3. Write the appraisal

Read the `BRIEF`. It carries the yardstick, the reader profile, the rules, and every session's moves with their evidence. Write the appraisal JSON to `RECAP_OUT`.

The rules that matter most: every item cites session and move ids; technical implications, not adjectives; minutes where the record has them; "unclear from the record" where it does not. The user asked for an appraisal, not a celebration.

## 4. Save

```bash
cartographer save "<RECAP_OUT>"
```

If it lists problems (an item without evidence, a praise word), fix the JSON and run it again.

## 5. Tell the user

In the configured voice: the verdict; what got them there; what cost them, with minutes; what was carried into the result and what it will cost later; one prompting pattern tied to the outcome; what to do next time. Then the replay path.
