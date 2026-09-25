"""User configuration: ~/.cartographer/config.json.

Everything the user can tune lives here. `effective()` resolves the `auto`
settings (voice, feedback focus) from the aptitude profile so the rest of the
code never has to.
"""
from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional, Tuple

HOME = os.environ.get("CARTOGRAPHER_HOME") or os.path.join(os.path.expanduser("~"), ".cartographer")
PATH = os.path.join(HOME, "config.json")

LEVELS = ("new", "intermediate", "advanced")
DEFAULTS: Dict[str, Any] = {
    "version": 2,
    "wrap": {
        "mode": "manual",          # manual | auto
        "idle_minutes": 30,        # for agents without a session-end event: wrap after this much quiet
        "min_prompts": 2,          # don't map sessions shorter than this
    },
    "profile": {
        "coding": "intermediate",    # new | intermediate | advanced
        "prompting": "intermediate", # new | intermediate | advanced
    },
    "feedback": {
        "enabled": True,
        "focus": "auto",           # prompts | code | both | auto
        "max_items": 4,
    },
    "voice": "auto",               # plain | technical | both | auto
    "privacy": {
        "keep_exact_prompts": True,
        "redact_secrets": True,
        "store_replies": False,    # keep agent replies verbatim in recaps (they can be long)
    },
    "projects": {"identity": "git"},   # git: repo = project, branches tracked | folder: the cwd is the project
    "agents": {  # enabled: include in sweeps; headless: override the command that maps a session non-interactively
        "claude-code": {"enabled": True, "headless": None},
        "codex": {"enabled": True, "headless": None},
        "cursor": {"enabled": True, "headless": None},
    },
}
ENUMS = {
    "privacy.keep_exact_prompts": (True, False),
    "wrap.mode": ("manual", "auto"),
    "profile.coding": LEVELS, "profile.prompting": LEVELS,
    "feedback.focus": ("prompts", "code", "both", "auto"),
    "voice": ("plain", "technical", "both", "auto"),
    "projects.identity": ("git", "folder"),
}


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load() -> Dict[str, Any]:
    try:
        with open(PATH, encoding="utf-8") as fh:
            return _merge(DEFAULTS, json.load(fh))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULTS)


def save(cfg: Dict[str, Any]) -> str:
    os.makedirs(HOME, exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    return PATH


def get(cfg: Dict[str, Any], dotted: str) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def coerce(raw: str) -> Any:
    low = raw.strip().lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    if raw.startswith(("[", "{")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw.strip()


def set_value(cfg: Dict[str, Any], dotted: str, raw: str) -> Any:
    value = coerce(raw) if isinstance(raw, str) else raw
    if dotted in ENUMS and value not in ENUMS[dotted]:
        raise ValueError("%s must be one of: %s" % (dotted, ", ".join(str(v).lower() for v in ENUMS[dotted])))
    parts = dotted.split(".")
    cur = cfg
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
        if not isinstance(cur, dict):
            raise KeyError(dotted)
    cur[parts[-1]] = value
    return value


def effective(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve `auto` settings from the aptitude profile."""
    coding = cfg["profile"]["coding"]
    prompting = cfg["profile"]["prompting"]
    voice = cfg["voice"]
    if voice == "auto":
        voice = "plain" if coding == "new" else "technical"
    focus = cfg["feedback"]["focus"]
    if focus == "auto":
        if prompting == "new" and coding != "advanced":
            focus = "prompts"
        elif coding == "advanced" and prompting == "advanced":
            focus = "both"
        elif coding == "advanced":
            focus = "prompts"
        elif prompting == "advanced":
            focus = "code"
        else:
            focus = "both"
    return {
        "coding": coding, "prompting": prompting, "voice": voice,
        "feedback": bool(cfg["feedback"]["enabled"]), "focus": focus,
        "max_feedback": int(cfg["feedback"].get("max_items", 4)),
        "keep_exact_prompts": bool(cfg["privacy"]["keep_exact_prompts"]),
        "store_replies": bool(cfg["privacy"].get("store_replies", False)),
        "wrap_mode": cfg["wrap"]["mode"],
    }


# The same questions drive the terminal wizard and the dashboard's setup form.
WIZARD: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("profile.coding", "How would you describe your coding experience?", LEVELS),
    ("profile.prompting", "And your experience prompting coding agents?", LEVELS),
    ("feedback.focus", "What should feedback focus on?", ENUMS["feedback.focus"]),
    ("voice", "How should the map speak?", ENUMS["voice"]),
    ("wrap.mode", "Wrap sessions yourself, or automatically when one ends?", ENUMS["wrap.mode"]),
    ("privacy.keep_exact_prompts", "Keep your exact prompt wording in maps?", ("true", "false")),
]
HELP = {
    "profile.coding": "new: maps in everyday words and feedback that explains what the code did. advanced: code-level feedback with files cited.",
    "profile.prompting": "new: concrete rewrites of your real prompts. advanced: prompt-architecture feedback tied to your numbers.",
    "feedback.focus": "prompts, code, both, or auto, which picks from the two answers above.",
    "voice": "plain = everyday words, technical = code terms, both = a toggle on every map, auto follows your coding level.",
    "wrap.mode": "manual: type /wrap at the end of a session. auto: a hook maps each Claude Code session when it ends.",
    "privacy.keep_exact_prompts": "false paraphrases your prompts in the map; the reading of them still works.",
}


def wizard(cfg: Dict[str, Any], ask=input, say=print) -> Dict[str, Any]:
    say("Cartographer setup. Press Enter to keep the value in brackets.\n")
    for key, question, options in WIZARD:
        current = get(cfg, key)
        current = ("true" if current else "false") if isinstance(current, bool) else current
        say("%s\n  %s" % (question, HELP[key]))
        while True:
            answer = ask("  %s [%s]: " % (" / ".join(options), current)).strip()
            if not answer:
                break
            try:
                set_value(cfg, key, answer)
                break
            except ValueError as exc:
                say("  %s" % exc)
        say("")
    return cfg
