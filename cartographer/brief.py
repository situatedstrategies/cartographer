"""Digest + config -> mapping brief.

The brief is a Markdown document any coding agent can follow to produce a
recap: who the reader is, how to speak to them, what Cartographer already
knows about the languages involved, the mapping rules, the schema, the
timeline, and where to write the result. Claude Code runs it through the
/wrap skill; Codex and Cursor get the same file via `cartographer brief`.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import config, lang, recap

VOICE_RULES = {
    "plain": (
        "Write every move in everyday words. Name a technical concept once with a short gloss in parentheses, then use "
        "the everyday word. Say what happened and why it mattered to the thing being built."),
    "technical": (
        "Write for someone who reads code. Use the real names of files, functions, libraries and errors. Be exact "
        "about what was tried and what changed. No glosses."),
    "both": (
        "Write the moves in technical register, and add a `plain` object on every move with the same four parts in "
        "everyday words (no jargon, one gloss per concept)."),
}
CODING_LEVEL = {
    "new": ("The user is new to coding. In coaching, explain what the agent's code did in plain terms and give one thing to "
            "check next time (run it, read the error, look at the test). Never assume they know the vocabulary."),
    "intermediate": ("The user can read code and knows the basics. Coaching can name patterns and files, and point at the "
                     "one concept that would have saved time."),
    "advanced": ("The user is an experienced engineer. Coaching should be code-level: architecture decisions the agent made "
                 "implicitly, risky patterns, missing tests, dependency choices, places where a review would object. "
                 "Cite files and symbols."),
}
PROMPTING_LEVEL = {
    "new": ("The user is new to prompting agents. Coaching on prompts should be encouraging and concrete: show what a "
            "more specific prompt would have produced, and give a rewritten version of a real prompt from this session. "
            "One idea per item. Prefer 'add the file name and the error text' over theory."),
    "intermediate": ("The user prompts competently. Coaching on prompts should point at leverage: anchoring, "
                     "done-conditions, decomposition, when to give the agent a plan versus a goal."),
    "advanced": ("The user prompts expertly. Coaching on prompts should be about prompt architecture: context loading, "
                 "constraint design, acceptance criteria, delegation boundaries, when to spec versus let the agent "
                 "explore, and where the prompting-profile numbers below say the session drifted."),
}
FOCUS_RULES = {
    "prompts": "Coaching items use focus 'prompt' (and 'workflow' when the lesson is about sequencing). Skip code critique.",
    "code": "Coaching items use focus 'code' (and 'workflow' when the lesson is about sequencing). Skip prompt critique.",
    "both": "Mix 'prompt', 'code' and 'workflow' items; lead with whichever cost the most time this session.",
}


def build(digest: Dict[str, Any], cfg: Dict[str, Any], recap_out: str, project_name: str = "") -> str:
    eff = config.effective(cfg)
    langs = [l["lang"] for l in digest.get("languages", [])][:5]
    notes = lang.notes_for(langs)
    proj = digest.get("project") or {}
    name = project_name or proj.get("name") or "(unknown project)"
    out: List[str] = []
    w = out.append

    w("# Cartographer mapping brief\n")
    w("You are Cartographer. Turn the session below into the story of **how the user built**, told to them in second person: "
      "what you did, what happened, what it meant, how you responded. Git records the code; you record the thinking. Use "
      "your own knowledge of the languages, frameworks and agent involved to read intent behind the prompts. Every move must "
      "be traceable to something in the timeline; never invent events.\n")

    w("## Session\n")
    w("- Agent: **%s**%s" % (digest.get("agent"), (" (model %s)" % digest["model"]) if digest.get("model") else ""))
    w("- Project: **%s** — %s%s" % (name, proj.get("id") or proj.get("root") or "no repo detected",
                                    "" if proj.get("exists", True) else " (folder no longer exists; this is a retrospective map)"))
    w("- Branch: %s%s" % (digest.get("branch") or "(none)",
                          ("; branches seen this session: " + ", ".join(digest.get("branches") or [])) if len(digest.get("branches") or []) > 1 else ""))
    w("- Duration: %s min · %s" % (digest.get("duration_min"), _stats_line(digest.get("stats") or {})))
    if langs:
        w("- Languages (by evidence): " + ", ".join("%s (%s)" % (l["lang"], "/".join(l["evidence"])) for l in digest["languages"][:6]))
    if digest.get("frameworks"):
        w("- Frameworks/tools named: " + ", ".join(f["name"] for f in digest["frameworks"][:10]))
    if digest.get("files"):
        w("- Files changed: " + ", ".join(digest["files"][:15]) + (" …" if len(digest["files"]) > 15 else ""))
    w("")

    w("## The yardstick\n")
    if digest.get("desired"):
        w("The user declared what done means for this version: **%s**\n" % digest["desired"])
        w("Judge every move against it. `outcome` on a move is provisional: how it looked at the time. The real verdict comes "
          "when the version is marked complete and appraised.\n")
    else:
        w("No desired outcome has been declared for this project, so there is no yardstick yet. Judge against the goal the user "
          "stated in the session, put that goal in `goal`, and say in `outcome` that none was declared. (`cartographer goal "
          "\"...\"` sets one; the appraisal at completion uses it.)\n")

    w("## Reader profile and register\n")
    w("- Coding aptitude: **%s**. %s" % (eff["coding"], CODING_LEVEL[eff["coding"]]))
    w("- Prompting aptitude: **%s**. %s" % (eff["prompting"], PROMPTING_LEVEL[eff["prompting"]]))
    w("- Voice: **%s**. %s" % (eff["voice"], VOICE_RULES[eff["voice"]]))
    if eff["feedback"]:
        w("- Feedback: **on**, focus **%s**, at most %d items. %s Each item names the move it refers to and, for prompt "
          "items, includes a `rewrite` of the actual prompt." % (eff["focus"], eff["max_feedback"], FOCUS_RULES[eff["focus"]]))
    else:
        w("- Feedback: **off**. Leave `coaching` empty. Patterns stay descriptive, not advisory.")
    w("- Exact prompts: **%s**." % ("keep them; put the exact wording in `prompt` on every move that started with one" if eff["keep_exact_prompts"]
                                     else "do not copy them; leave `prompt` out and paraphrase in `you`"))
    w("")

    if notes:
        w("## What Cartographer knows about these languages\n")
        w("Use these as priors when reading the prompts. Your own knowledge applies on top.\n")
        for l, note in notes.items():
            w("- **%s** — %s" % (l, note))
        w("")

    p = digest.get("prompting") or {}
    if p.get("prompts"):
        w("## Prompting profile (mechanical signals, this session)\n")
        w("- %d prompts, avg %s words, avg specificity %s/3, anchored %s, vague %s, delegating %s, with done-condition %s, "
          "pasted code %s, repairs of the agent's previous turn %s, bare go-aheads %s"
          % (p["prompts"], p["avg_words"], p["avg_specificity"], _pct(p["anchored_ratio"]), _pct(p["vague_ratio"]), _pct(p["delegation_ratio"]),
             _pct(p["acceptance_ratio"]), _pct(p["pasted_code_ratio"]), _pct(p.get("repair_ratio")), _pct(p.get("accept_ratio"))))
        w("- Intent mix: " + ", ".join("%s %d" % kv for kv in p["intent_mix"].items()))
        if p.get("top_signals"):
            w("- Most common signals: " + "; ".join(p["top_signals"]))
        w("\nThese are detector outputs. Treat them as hints and correct them from the actual text.\n")

    w("## Mapping rules\n")
    w("- **Phases**: 2–6 per session, named by what the user was doing (Explore, Plan, Scaffold, Build UI, Debug auth, "
      "Polish, Ship…). They are the chapters of the story. If the branch changed, note the branch on the phase.")
    w("- **Moves**: 5–20. A move is one round with consequences, written to the user in second person, past tense: `you` "
      "(what you did, one sentence: 'You asked for…'), `happened` (what the agent did and what resulted, one or two concrete "
      "sentences), `consequence` (what that meant for the build), `outcome` (one word: worked, partly, broke, wrong_way, "
      "opened), `response` (how you responded: accepted it, repaired it, went back, changed direction; usually the next "
      "move's `you` seen from here). Several prompts that continued one line of work share a move; a prompt that changed "
      "direction always starts one. When the agent worked for a long stretch without a prompt, say so in `you`. Skip routine "
      "tool calls. `t` is minutes from start.")
    w("- **Marks**: tag turning points with `mark`: decision (a choice between options), dead_end (abandoned), fix (what "
      "unblocked), pivot (change of framing), insight (a realization), question (investigation before acting), artifact "
      "(something made). Leave it out on ordinary moves.")
    w("- **Read the response honestly**: the detector marks the next prompt as accept, repair or something else. A repair "
      "means the previous move went wrong for the user even if the code ran; say so in that move's `outcome` and `consequence`.")
    w("- **Honest appraisal**: every `consequence` names the technical implication: what the choice committed the project to "
      "(a dependency, a data shape, a shortcut left in, a test not written) and what it cost or saved, in minutes where the "
      "timeline shows it. No praise words and no softening; a detour is called a detour. Where the record does not show "
      "something, write 'unclear from the record' instead of guessing.")
    w("- **Evidence**: every move lists `evidence`: the timeline items it rests on, as written there ('prompt #3', 'error at "
      "12.4m', 'pause 19m', 'repair at 20.1m'). A move without evidence is invented, and `save` rejects praise words.")
    w("- **Branches**: set `branch` on moves when the session touched more than one.")
    w("- **Language-aware reading**: when a prompt uses aesthetic or physical words (\"snappier\", \"cleaner\", \"make it "
      "pop\"), map what the agent *interpreted* them as, in the target language's terms. When a fix loop is really a "
      "toolchain or environment issue, say so; that is a different lesson from a code bug.")
    w("- **Patterns**: specific and honest, in neutral phrasing (\"Starts from the data model\", \"Accepts the first design "
      "the agent proposes\"). Include habits that cost time.")
    w("- **Reusable prompts**: only prompts that worked, generalized with `<placeholders>`, with the language they suit.")
    w("- **Time sinks**: where the minutes went, including productive pauses.")
    w("- Never copy secrets, keys, tokens, or personal data into the recap.\n")

    w("## Recap format\n")
    w("Write JSON with exactly this shape (values are placeholders):\n")
    w("```json\n%s\n```\n" % json.dumps(recap.EXAMPLE, indent=1, ensure_ascii=False))
    w("`outcome` ∈ %s. `mark` ∈ %s (optional). `coaching[].focus` ∈ %s.\n" % (", ".join(recap.OUTCOMES), ", ".join(recap.MARKS), ", ".join(recap.FOCUS)))

    w("## Timeline\n")
    w("`t` is minutes from session start. `read:` lines are the detector's reading of each prompt.\n")
    for item in digest.get("timeline", []):
        w(_timeline_line(item))
    w("")

    w("## Output\n")
    w("1. Write the recap JSON to `%s`." % recap_out)
    w("2. Run: `cartographer save \"%s\"` — it validates, redacts secrets, files the recap under the project and renders the replay. "
      "If it reports problems, fix the JSON and run it again. Replace every placeholder from the example; ones left as-is are "
      "filled from the session where possible and rejected otherwise." % recap_out)
    w("3. Tell the user, in the configured voice, as a short story in second person: one line on what the session "
      "accomplished; 3–5 beats of 'you did X, Y happened, so Z, and you responded with W'; one 'how you build' observation; "
      "the coaching items if feedback is on; the replay path.")
    return "\n".join(out)


def _stats_line(s: Dict[str, Any]) -> str:
    parts = []
    for key, label in (("prompts", "prompts"), ("replies", "replies"), ("tool_calls", "tool calls"), ("errors", "errors"),
                       ("files_touched", "files changed"), ("branch_changes", "branch changes")):
        if s.get(key):
            parts.append("%s %s" % (s[key], label))
    return ", ".join(parts) or "no activity"


def _pct(x: float) -> str:
    return "%d%%" % round(100 * (x or 0))


def _timeline_line(item: Dict[str, Any]) -> str:
    t = "%6s" % ("" if item.get("t") is None else "%.1f" % item["t"])
    k = item["kind"]
    if k == "prompt":
        extra = ""
        if item.get("attached"):
            extra += " [attached: %s]" % ", ".join(item["attached"])
        if item.get("pasted"):
            extra += " [pasted content]"
        text = item["text"].replace("\n", "\n         ")
        return "%s  PROMPT #%d%s\n         %s\n         read: %s" % (t, item["n"], extra, text, item["read"])
    if k == "reply":
        return "%s  reply: %s" % (t, item["text"])
    if k == "tools":
        return "%s  tools: %s" % (t, " | ".join(item["calls"]))
    if k == "error":
        return "%s  ERROR (%s): %s" % (t, item.get("tool"), item["text"])
    if k == "branch":
        return "%s  BRANCH -> %s (from %s)" % (t, item["to"], item.get("from") or "?")
    if k == "pause":
        return "%s  pause: %d min of no activity" % (t, item["minutes"])
    return "%s  note: %s" % (t, item.get("text", ""))


def build_appraisal(entry: Dict[str, Any], version: Dict[str, Any], recaps: List[Dict[str, Any]], cfg: Dict[str, Any], out_path: str) -> str:
    """The end-of-version brief: judge every session's moves against the declared desired outcome."""
    eff = config.effective(cfg)
    out: List[str] = []
    w = out.append
    w("# Cartographer appraisal brief\n")
    w("You are Cartographer. **%s** version **%s** has been marked complete (result: **%s**). Judge the whole build against the "
      "desired outcome the user declared, using only the session maps below as evidence. This is an appraisal, not a celebration: "
      "the user asked for an honest reading of how they worked and prompted, what it cost, and what it produced.\n"
      % (entry.get("name"), version.get("name"), version.get("result")))
    w("## The yardstick\n")
    w("- Desired outcome (declared %s): **%s**" % ((version.get("set_at") or "?")[:10],
      version.get("desired") or "never declared. Say so in the verdict, and judge against the goals the sessions state."))
    w("- Result: **%s**. What actually happened, in the user's words: %s\n" % (version.get("result"), version.get("actual") or "(not given)"))
    w("## Reader profile and register\n")
    w("- Coding aptitude: **%s**. %s" % (eff["coding"], CODING_LEVEL[eff["coding"]]))
    w("- Prompting aptitude: **%s**. %s" % (eff["prompting"], PROMPTING_LEVEL[eff["prompting"]]))
    w("- Voice: **%s**. %s\n" % (eff["voice"], VOICE_RULES[eff["voice"]]))
    w("## Rules\n")
    w("- **Evidence**: every item cites the moves it rests on as `session <id> <move id>` (ids as given below). Items without "
      "evidence are rejected by `save`.")
    w("- **Technical implications**: `carried_forward` names what is now in the result because of a move (a shortcut, a "
      "dependency, a data shape, a missing test) and what it will cost later. Cite the move that put it there.")
    w("- **Minutes** come from the sessions: durations, time sinks, move times. Do not estimate what the record does not show.")
    w("- **Record versus inference**: say what the record shows; when you infer, say 'likely' and why.")
    w("- **Prompting**: tie each pattern to its effect on the outcome, using the sessions' prompt readings and repair turns. "
      "Neutral phrasing, no praise words, no softening.")
    w("- Never copy secrets, keys, tokens, or personal data.\n")
    w("## Format\n")
    w("Write JSON with exactly this shape (values are placeholders):\n")
    w("```json\n%s\n```\n" % json.dumps(recap.APPRAISAL_EXAMPLE, indent=1, ensure_ascii=False))
    w("Set `project` to `%s`, `version` to `%s`, `result` to `%s`, and copy `desired` and `actual` from the yardstick.\n"
      % (json.dumps({"id": entry.get("id"), "name": entry.get("name")}), version.get("name"), version.get("result")))
    w("## Sessions (%d)\n" % len(recaps))
    for r in recaps:
        sid = (r.get("session_id") or "")[:8]
        w("### session %s · %s · %s · %s min · %s" % (sid, r.get("date"), r.get("title"), r.get("duration_min"), r.get("agent")))
        w("- goal: %s" % r.get("goal"))
        w("- outcome at the time: %s" % r.get("outcome"))
        for m in r.get("moves") or []:
            bits = ["%s t=%s [%s%s]" % (m.get("id"), m.get("t"), m.get("outcome"), (", " + m["mark"]) if m.get("mark") else "")]
            for key in ("you", "happened", "consequence", "response"):
                if m.get(key):
                    bits.append("%s: %s" % (key, m[key]))
            if m.get("evidence"):
                bits.append("evidence: " + "; ".join(m["evidence"]))
            w("  - " + " | ".join(bits))
        if r.get("time_sinks"):
            w("- time sinks: " + "; ".join("%s (%s min)" % (t.get("what"), t.get("minutes")) for t in r["time_sinks"]))
        if r.get("patterns"):
            w("- patterns noted then: " + "; ".join(r["patterns"]))
        p = r.get("prompting") or {}
        if p.get("prompts"):
            w("- prompting numbers: %d prompts, specificity %s/3, anchored %s, vague %s, repairs %s, go-aheads %s"
              % (p["prompts"], p.get("avg_specificity"), _pct(p.get("anchored_ratio")), _pct(p.get("vague_ratio")), _pct(p.get("repair_ratio")), _pct(p.get("accept_ratio"))))
        w("")
    w("## Output\n")
    w("1. Write the appraisal JSON to `%s`." % out_path)
    w("2. Run: `cartographer save \"%s\"` — it validates (evidence on every item, no praise words), files the appraisal under the "
      "project and renders the replay with it. If it reports problems, fix the JSON and run it again." % out_path)
    w("3. Tell the user, in the configured voice: the verdict; what got them there; what cost them, with minutes; what was carried "
      "into the result and what it will cost later; one prompting pattern tied to the outcome; what to do next time; the replay path.")
    return "\n".join(out)
