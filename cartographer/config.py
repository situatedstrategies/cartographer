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
    "projects": {
        "identity": "git",         # git (repo = project, branches tracked) | folder
        "track_branches": True,
    },
    "agents": {
        "claude-code": {"enabled": True, "headless": None},
        "codex": {"enabled": True, "headless": None},
        "cursor": {"enabled": True, "headless": None},
    },
    "sync": {"enabled": False, "endpoint": None, "team": None},
    "language": "en",
}
ENUMS = {
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
        raise ValueError("%s must be one of: %s" % (dotted, ", ".join(ENUMS[dotted])))
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
        "track_branches": bool(cfg["projects"].get("track_branches", True)),
        "wrap_mode": cfg["wrap"]["mode"],
    }


WIZARD: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("profile.coding", "How would you describe your coding experience?", LEVELS),
    ("profile.prompting", "And your experience prompting coding agents?", LEVELS),
    ("feedback.focus", "What should feedback focus on? (auto picks from the two answers above)", ENUMS["feedback.focus"]),
    ("voice", "How should the map speak? plain = everyday words, technical = code terms, both = a toggle", ENUMS["voice"]),
    ("wrap.mode", "Wrap sessions manually (/wrap) or automatically when a session ends?", ENUMS["wrap.mode"]),
]


def wizard(cfg: Dict[str, Any], ask=input, say=print) -> Dict[str, Any]:
    say("Cartographer setup. Press Enter to keep the value in brackets.\n")
    for key, question, options in WIZARD:
        current = get(cfg, key)
        while True:
            answer = ask("%s\n  %s [%s]: " % (question, " / ".join(options), current)).strip()
            if not answer:
                break
            try:
                set_value(cfg, key, answer)
                break
            except ValueError as exc:
                say("  %s" % exc)
    keep = ask("Keep your exact prompt wording in recaps? [%s]: " % ("yes" if cfg["privacy"]["keep_exact_prompts"] else "no")).strip()
    if keep:
        cfg["privacy"]["keep_exact_prompts"] = coerce(keep) is True
    return cfg
