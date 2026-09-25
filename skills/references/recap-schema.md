# Recap schema (`cartographer.session/v2`)

One recap per session. Written by the mapping agent, validated by `cartographer save`.

| Field | Meaning |
|---|---|
| `agent`, `session_id` | which agent made the session, and its id (filled from the digest if omitted) |
| `project` | `{id, name, root, remote}`; id is the normalized git remote (`github.com/me/app`) or `local:<path>` |
| `branch`, `branches` | branch at start; every branch seen |
| `title`, `date`, `started_at`, `ended_at`, `duration_min` | session facts |
| `goal`, `outcome` | what they set out to do, in their terms; where it landed |
| `voice` | `plain` or `technical`: the register the map is written in |
| `languages`, `frameworks`, `files`, `tags` | evidence for matching similar projects later |
| `phases[]` | `{name, summary, branch?}`; 2–6; columns in the replay |
| `steps[]` | see below; 6–25 |
| `reusable_prompts[]` | `{prompt, why, language?}`; templates with `<placeholders>` that worked |
| `patterns[]` | neutral observations about how this person builds |
| `time_sinks[]` | `{what, minutes}` |
| `coaching[]` | `{focus: prompt\|code\|workflow, observation, suggestion, rewrite?, step?}`; empty when feedback is off |
| `next_steps[]` | unfinished work phrased for the next session |
| `prompting` | mechanical prompting profile copied from the digest |

## Steps

```json
{"id": "s7", "t": 19.6, "phase": "Decide", "branch": "main", "kind": "decision",
 "title": "Ship solo and teams tiers", "detail": "…",
 "plain": {"title": "…", "detail": "…"},
 "prompt": "exact wording, when the phrasing is the lesson",
 "files": ["src/auth.ts"], "links": [{"to": "s4", "rel": "reverted"}]}
```

`kind`: `prompt` (a message that set direction) · `question` (investigation before acting) · `decision` (a choice between options) · `dead_end` (abandoned, link to what replaced it) · `fix` (what unblocked) · `artifact` (something made) · `pivot` (change of framing) · `insight` (realization).

`rel`: `led_to` · `blocked_by` · `reverted` · `reused` · `answered`. Consecutive steps are joined automatically; add links only when they say something the sequence doesn't.
