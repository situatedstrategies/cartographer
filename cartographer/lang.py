"""Language detection and prompt pragmatics.

1. Which languages and frameworks a session touched: from the files the agent
   edited, the code the user pasted, and the names the user used.
2. How each prompt does its work: the act it performs (build, fix, repair,
   accept, ask...), what it anchors to, how specific it is, where it hedges or
   delegates. These are mechanical signals for the mapping model, not verdicts.

`LANGUAGE_NOTES` are short priors on how prompts about each language behave;
the brief includes the ones for the languages a session actually used, so old
sessions can be mapped with the same context as live ones.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

LANGS = {  # language -> file extensions
    "python": "py pyi ipynb", "javascript": "js mjs cjs jsx", "typescript": "ts tsx mts", "html": "html htm",
    "css": "css scss sass less", "vue": "vue", "svelte": "svelte", "rust": "rs", "go": "go", "java": "java",
    "kotlin": "kt kts", "swift": "swift", "objective-c": "m mm", "c": "c h", "cpp": "cpp cc hpp", "csharp": "cs",
    "ruby": "rb", "php": "php", "elixir": "ex exs", "haskell": "hs", "scala": "scala", "clojure": "clj", "lua": "lua",
    "dart": "dart", "r": "r", "julia": "jl", "zig": "zig", "gdscript": "gd", "sql": "sql prisma", "graphql": "graphql gql",
    "shell": "sh bash zsh fish", "powershell": "ps1", "yaml": "yml yaml", "toml": "toml", "json": "json", "xml": "xml",
    "markdown": "md mdx rst", "text": "txt", "docker": "dockerfile", "terraform": "tf hcl", "nix": "nix",
    "shader": "glsl wgsl hlsl frag vert", "solidity": "sol", "config": "ini env cfg conf",
}
EXT_LANG = {ext: lang for lang, exts in LANGS.items() for ext in exts.split()}
FENCE_ALIAS = {"js": "javascript", "jsx": "javascript", "ts": "typescript", "tsx": "typescript", "py": "python", "sh": "shell",
               "bash": "shell", "zsh": "shell", "console": "shell", "yml": "yaml", "rs": "rust", "golang": "go", "c++": "cpp",
               "c#": "csharp", "cs": "csharp", "objc": "objective-c", "txt": "text", "": "text"}
MENTIONS = {  # names people use in prose
    "python": r"\bpython\b|\bpandas\b|\bfastapi\b|\bdjango\b|\bflask\b|\bpip\b|\bvenv\b",
    "typescript": r"\btypescript\b|\bts\b(?!x)|\btsx\b", "javascript": r"\bjavascript\b|\bjs\b|\bnode(?:js)?\b|\bnpm\b|\bpnpm\b",
    "html": r"\bhtml\b|\bmarkup\b", "css": r"\bcss\b|\btailwind\b|\bstyles?heet\b",
    "rust": r"\brust\b|\bcargo\b|\bborrow checker\b", "go": r"\bgolang\b|\bgoroutine\b|\bgo (?:module|routine|func)\b",
    "swift": r"\bswift(?:ui)?\b|\bxcode\b", "kotlin": r"\bkotlin\b|\bandroid\b|\bjetpack\b",
    "java": r"\bjava\b(?!script)|\bspring\b|\bmaven\b|\bgradle\b", "csharp": r"\bc#\b|\bcsharp\b|\b\.net\b|\bunity\b",
    "cpp": r"\bc\+\+\b|\bcpp\b", "ruby": r"\bruby\b|\brails\b", "php": r"\bphp\b|\blaravel\b",
    "sql": r"\bsql\b|\bpostgres(?:ql)?\b|\bsqlite\b|\bmysql\b", "shell": r"\bbash\b|\bshell script\b|\bzsh\b",
    "gdscript": r"\bgodot\b|\bgdscript\b", "dart": r"\bflutter\b|\bdart\b", "elixir": r"\belixir\b|\bphoenix\b",
    "lua": r"\blua\b|\bl[öo]ve2d\b|\broblox\b", "shader": r"\bshaders?\b|\bglsl\b|\bwgsl\b",
    "yaml": r"\byaml\b|\bgithub actions\b", "docker": r"\bdocker(?:file)?\b", "terraform": r"\bterraform\b",
}
FRAMEWORKS = [  # (pattern, name, language)
    (r"\bnext\.?js\b|\bapp router\b", "Next.js", "typescript"), (r"\bexpo\b|\breact native\b", "React Native", "typescript"),
    (r"\breact(?:\.js)?\b(?!\s+native)|\bjsx\b|\buseState\b", "React", "javascript"), (r"\bvue\b|\bnuxt\b", "Vue", "javascript"),
    (r"\bsvelte(?:kit)?\b", "Svelte", "javascript"), (r"\bexpress\b", "Express", "javascript"), (r"\btailwind\b", "Tailwind", "css"),
    (r"\bthree\.?js\b|\bwebgl\b", "Three.js / WebGL", "javascript"), (r"\bdjango\b", "Django", "python"), (r"\bflask\b", "Flask", "python"),
    (r"\bfastapi\b", "FastAPI", "python"), (r"\bpandas\b|\bnumpy\b", "pandas / NumPy", "python"), (r"\bpytorch\b|\btorch\b", "PyTorch", "python"),
    (r"\brails\b", "Rails", "ruby"), (r"\blaravel\b", "Laravel", "php"), (r"\bspring boot\b", "Spring Boot", "java"),
    (r"\bswiftui\b", "SwiftUI", "swift"), (r"\bjetpack compose\b", "Compose", "kotlin"), (r"\bflutter\b", "Flutter", "dart"),
    (r"\bunity\b", "Unity", "csharp"), (r"\bgodot\b", "Godot", "gdscript"), (r"\bsupabase\b", "Supabase", "sql"),
    (r"\bfirebase\b", "Firebase", "javascript"), (r"\bprisma\b", "Prisma", "typescript"), (r"\bpostgres(?:ql)?\b", "Postgres", "sql"),
    (r"\bsqlite\b", "SQLite", "sql"), (r"\bdocker\b", "Docker", "docker"), (r"\bgithub actions\b", "GitHub Actions", "yaml"),
    (r"\bstripe\b", "Stripe", "javascript"), (r"\bopenai\b|\banthropic\b|\bclaude api\b|\bllm\b", "LLM API", "python"),
    (r"\bmcp\b|\bmodel context protocol\b", "MCP", "typescript"), (r"\belectron\b|\btauri\b", "Desktop shell", "typescript"),
]

# Priors for the mapping model: where ambiguity hides, what dead ends look like, what a good prompt carries.
LANGUAGE_NOTES: Dict[str, str] = {
    "python": ("Terse, task-first prompts. Ambiguity hides in the environment (interpreter, venv, package manager); dead ends "
               "cluster around imports and silent None / str-vs-bytes mismatches. 'Pythonic' and 'clean' ask for idiom, not behavior."),
    "javascript": ("Prompts describe behavior in UI terms ('when I click'); 'state' and 'async' mean different things per framework, "
                   "and the agent picks one if the user doesn't. Dead ends: bundler config, async ordering, dependency churn."),
    "typescript": ("JavaScript plus a second conversation with the type checker. 'Fix the types' loops are common, and reaching for "
                   "`any` under time pressure is a decision worth mapping."),
    "html": ("Visual, comparative prompts ('like this site', 'more modern'), often with screenshots. The agent guesses at aesthetics "
             "and the user corrects by feel; layout fights (centering, overflow, breakpoints) are the classic dead end."),
    "css": ("Aesthetic words ('cleaner', 'breathing room', 'pop') map poorly onto properties, so expect several rounds. Specificity "
            "and cascade collisions are the silent dead end."),
    "rust": ("The compiler drives the session: borrow-checker loops dominate, and `.clone()` or `unwrap()` escapes are decisions. "
             "Good prompts state ownership intent."),
    "go": "Prompts are about structure and concurrency. Errors are explicit, so dead ends are usually design (packages, interfaces), not syntax.",
    "swift": ("Xcode shapes the session: build errors, previews, signing, simulator state the agent can't see. SwiftUI state "
              "ownership (@State vs @Binding vs observable) is the recurring dead end."),
    "kotlin": "Android sessions spend much of their time on Gradle and SDK versions rather than logic. Good prompts pin AGP and min SDK.",
    "java": "Structural prompts (services, layers, annotations). Build tools and framework magic create dead ends that look like code bugs.",
    "csharp": ("Unity sessions are about lifecycle and editor state the agent can't see, and game-feel words ('snappier') need numbers "
               "to converge; .NET sessions are about DI and configuration."),
    "gdscript": "Prompts that name nodes and paths converge fast; ones that don't produce guesses. Editor-side setup is a dead end because the agent only touches files.",
    "sql": "Declarative prompts whose risk is semantic: joins that multiply rows, NULLs, timezones. Good prompts include the schema or a sample row and the expected shape.",
    "shell": "Imperative one-liners. The danger is scope ('clean up' can delete), quoting, and macOS-vs-Linux tools.",
    "yaml": "CI prompts are outcome-shaped ('make tests run on push') and the cost is the remote feedback loop. Good prompts paste the failing job log.",
    "docker": "Getting something to run somewhere else. Dead ends: base images, build context, ports and volumes.",
    "dart": "Widget-tree prompts; the state-management choice is usually implicit and worth mapping as a decision.",
    "shader": "Visual and physical prompts ('glowy', 'wobble') iterated by eye. Numeric parameters and screenshots are the useful anchors.",
    "markdown": "Docs prompts are about audience and tone; the ambiguity is 'who is this for'.",
    "config": "Configuration prompts are about environments; ask which machine or stage before calling a dead end a bug.",
}

# --- prompt reading -------------------------------------------------------------------------------------------
_split = lambda s: s.split("|")  # noqa: E731
INTENTS = {k: _split(v) for k, v in {
    "build": "build|rebuild|create|make|add|implement|write|generate|scaffold|set up|new|start|prototype|feature",
    "fix": "fix|bug|broken|doesn't work|does not work|not working|error|crash|fails|failing|wrong|isn't|won't",
    "refactor": "refactor|refine|clean|reorganize|simplify|rename|extract|move|split|dedupe|tidy|restructure|leaner|lighter",
    "explain": "explain|what does|why does|how does|walk me through|understand|what is|meaning",
    "explore": "look at|find|where is|search|check|investigate|inspect|list|show me|read|look into|open",
    "test": "test|tests|coverage|spec|assert|unit|e2e",
    "config": "configure|install the|dependency|dependencies|env var|environment variable|config file|dotfile|package.json|requirements.txt|pyproject",
    "deploy": "deploy|ship|release|publish|docker|ci|pipeline|production|host",
    "design": "design|layout|style|css|ui|ux|font|color|colour|responsive|animation|theme|polish|nicer|prettier|modern|spacing",
    "review": "review|audit|critique|check for|security|lint|feedback on",
    "plan": "plan|architecture|approach|options|tradeoff|trade-off|should we|think through|spec|outline|roadmap",
    "articulate": "articulate|help me describe|put into words|pitch|explain my idea|concept",
}.items()}
PRIORITY = ("fix", "design", "refactor", "test", "deploy", "config", "review", "plan", "articulate", "explain", "explore", "build")
# Turn-initial repair of the agent's previous turn, and short go-aheads. Both are about the turn before, not new work.
REPAIR_OPEN = _split("no,|no.|nope|not that|i meant|that's not|thats not|not what i|wrong one|wait,|hold on")
REPAIR_ANY = _split("undo that|undo the last|revert that|revert the last|go back to|put it back|put that back")
ACCEPT_OPEN = _split("yes|yep|yeah|ok|okay|sure|go ahead|do it|proceed|continue|looks good|lgtm|perfect|great|sounds good|approved|ship it|good|nice|thanks")
VAGUE = _split("make it better|doesn't work|does not work|not working|fix it|clean up|nicer|make it pop|something like|somehow|and stuff|"
               "kind of|sort of|whatever|just make|look good|look nice|modern|sleek|professional|cool|better|improve it|it's broken|weird|off|janky|buggy")
DELEGATE = _split("you decide|your call|whatever you think|use your judgment|use your judgement|up to you|however you want|pick the best|do what makes sense|you choose|surprise me")
HEDGES = _split("maybe|i think|perhaps|possibly|might|not sure|i guess|probably|could we")
LARGE = _split("entire|whole|full|complete|from scratch|end to end|end-to-end|all of|everything|mvp")
SMALL = _split("small|quick|tiny|just|one line|minor|little|only")
DONE = _split("should return|should show|should display|expect|so that|until|passes|works when|must|output should|test passes|acceptance|when i|then it|verify")
CONSTRAINT = _split("must|should|never|only|don't|do not|without|keep|avoid|make sure|always|instead of|not allowed")
EXAMPLE = _split("for example|e.g.|like this|example:|here's an example|such as|similar to")
QUESTION_START = ("what", "why", "how", "where", "when", "which", "who", "can", "could", "should", "is", "are", "does", "do", "would", "will", "any")
VERBS = set(_split("add|build|create|make|fix|write|implement|refactor|change|update|remove|delete|move|rename|run|test|check|look|find|explain|show|"
                   "generate|set|install|deploy|design|convert|turn|give|help|let's|lets|please|go|try|use|replace|extract|clean|rewrite|review|plan|"
                   "start|continue|keep|stop|open|read|search|list|describe|draft|put|refine|simplify"))
SYMBOL_RE = re.compile(r"`[^`\n]{2,60}`|\b[a-zA-Z_]\w*\(\)|\b[a-z]+[A-Z]\w*\b|\b[a-z]+_[a-z_]+\b|\b\w+\.\w+\.\w+\b")
PATH_RE = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8})(?![\w/])")
FILE_RE = re.compile(r"(?<![\w/.@-])([\w-]+\.(?:%s))(?![\w/])" % "|".join(sorted(EXT_LANG, key=len, reverse=True)))
NOT_FILES = {"node.js", "next.js", "vue.js", "three.js", "react.js", "express.js", "e.g", "i.e"}
LINE_RE = re.compile(r"\bline\s+\d+|:\d+(?::\d+)?\b")
URL_RE = re.compile(r"https?://\S+")
ERROR_RE = re.compile(r"Traceback|Error:|error\[E\d+\]|Exception|TypeError|ReferenceError|SyntaxError|panic|Segmentation|exit code|ENOENT|ECONN|undefined is not", re.I)


def _count(text: str, phrases: Iterable[str]) -> List[str]:
    """Phrases present in text, tolerant of simple inflections (color/colors, look/looking)."""
    t = text.lower()
    return [p for p in phrases if re.search(r"(?<![a-z])" + re.escape(p) + r"(?:s|es|ed|ing)?(?![a-z])", t)]


def lang_of_file(path: str) -> Optional[str]:
    base = os.path.basename(path).lower()
    if base.startswith("dockerfile"):
        return "docker"
    if base in ("makefile", "cmakelists.txt") or base.startswith(".env"):
        return "config"
    return EXT_LANG.get(base.rsplit(".", 1)[-1]) if "." in base else None


def detect_languages(files: Iterable[str], fences: Iterable[str], texts: Iterable[str]) -> List[Dict[str, Any]]:
    """Rank languages by evidence: files count most, then pasted code, then names in prose."""
    score: Counter = Counter()
    sources: Dict[str, set] = {}

    def add(lang, n, src):
        if lang:
            score[lang] += n
            sources.setdefault(lang, set()).add(src)

    for f in files:
        add(lang_of_file(f), 3, "files")
    for tag in fences:
        lang = FENCE_ALIAS.get(tag, tag)
        add(lang if lang in LANGS and lang != "text" else None, 2, "pasted code")
    joined = "\n".join(t.lower() for t in texts)
    for lang, pattern in MENTIONS.items():
        hits = len(re.findall(pattern, joined, flags=re.I))
        if hits:
            add(lang, min(hits, 5), "mentions")
    return [{"lang": lang, "score": n, "evidence": sorted(sources[lang])} for lang, n in score.most_common()
            if not (lang in ("text", "markdown", "json") and len(score) > 1)]


def detect_frameworks(texts: Iterable[str], files: Iterable[str]) -> List[Dict[str, str]]:
    joined = ("\n".join(texts) + "\n" + "\n".join(files)).lower()
    return [{"name": name, "lang": lang} for pattern, name, lang in FRAMEWORKS if re.search(pattern, joined, flags=re.I)]


def analyze_prompt(text: str) -> Dict[str, Any]:
    """Mechanical reading of one prompt. Everything here is a signal, not a verdict."""
    raw = text or ""
    lower = raw.lower().strip()
    first = re.sub(r"^[^a-z]+", "", lower.split("\n", 1)[0])[:40]
    words = len(raw.split())
    fences = re.findall(r"```([A-Za-z0-9_+#.-]*)", raw)
    prose = re.sub(r"```.*?```", " ", raw, flags=re.S)
    paths = [p for p in PATH_RE.findall(prose) if not p.startswith("http")]
    paths += [f for f in FILE_RE.findall(prose) if f.lower() not in NOT_FILES and f not in paths]
    symbols = [s for s in SYMBOL_RE.findall(prose) if len(s) > 2 and not re.fullmatch(r"[\d.]+", s)][:12]
    urls = len(URL_RE.findall(prose))
    has_error = bool(ERROR_RE.search(raw))
    lines = bool(LINE_RE.search(prose))
    opening = prose.lstrip()[:80].lower()

    scores = {intent: len(_count(prose, phrases)) for intent, phrases in INTENTS.items()}
    if has_error:
        scores["fix"] += 2
    best = max(scores.items(), key=lambda kv: (kv[1], -PRIORITY.index(kv[0])))
    is_question = prose.strip().endswith("?") or first.split(" ")[0] in QUESTION_START
    repair = _count(opening, REPAIR_OPEN) + _count(prose, REPAIR_ANY)
    accept = words <= 8 and best[1] == 0 and bool(_count(opening[:30], ACCEPT_OPEN))
    if repair:
        intent = "repair"
    elif best[1] > 0:
        intent = best[0]
    elif accept:
        intent = "accept"
    else:
        intent = "ask" if is_question else "other"
    if is_question and intent == "explore" and scores["explain"] == 0:
        intent = "ask"

    if (first.split(" ")[0] in VERBS if first else False) or "please" in lower[:60]:
        mode = "imperative"
    elif is_question:
        mode = "question"
    elif any(w in lower for w in ("i want", "i'd like", "i need", "it should", "we need", "the goal", "idea")):
        mode = "descriptive"
    else:
        mode = "mixed"

    constraints, done, vague = _count(prose, CONSTRAINT), _count(prose, DONE), _count(prose, VAGUE)
    delegate, hedges, examples = _count(prose, DELEGATE), _count(prose, HEDGES), _count(prose, EXAMPLE)
    langs = [lang for lang, pat in MENTIONS.items() if re.search(pat, prose, flags=re.I)]
    fws = [f["name"] for f in detect_frameworks([prose], [])]

    anchored = bool(paths or symbols or lines or urls or has_error)
    specificity = int(anchored) + int(bool(constraints or done)) + int(bool(fences or examples or langs or fws))
    if vague and not anchored:
        specificity = max(0, specificity - 1)
    scope = "large" if _count(prose, LARGE) else ("small" if (_count(prose, SMALL) or words < 12) else "medium")

    signals = []  # concrete coaching opportunities, phrased for the mapping model
    if intent == "repair":
        signals.append("repair turn: corrects the agent's previous turn; the ambiguity was in the prompt before this one")
    if intent == "fix" and not has_error and not paths:
        signals.append("fix request without the error text or a file: the agent had to guess where the bug lives")
    if vague and not anchored:
        signals.append("aesthetic or vague wording (%s) with nothing to anchor it" % ", ".join(vague[:3]))
    if scope == "large" and specificity <= 1:
        signals.append("large scope with little detail: the agent chose the architecture")
    if delegate:
        signals.append("explicit delegation (%s): decisions moved to the agent" % delegate[0])
    if intent == "build" and not done and words > 20:
        signals.append("no stated done-condition: success was judged by feel")
    if fences and intent in ("fix", "explain"):
        signals.append("pasted code: strong anchor, good practice")
    if paths and (constraints or done):
        signals.append("anchored and constrained: a high-precision prompt")

    return {
        "words": words, "mode": mode, "intent": intent, "scope": scope, "specificity": specificity,
        "anchors": {"paths": paths[:8], "symbols": symbols[:8], "line_refs": lines, "urls": urls, "error_text": has_error},
        "constraints": len(constraints), "acceptance": bool(done), "examples": bool(examples),
        "vague": vague[:4], "delegation": bool(delegate), "hedges": len(hedges),
        "code_blocks": [FENCE_ALIAS.get(f.lower(), f.lower()) for f in fences],
        "languages": langs, "frameworks": fws, "signals": signals,
    }


def aggregate(profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(profiles)
    if not n:
        return {"prompts": 0}
    ratio = lambda pred: round(sum(1 for p in profiles if pred(p)) / n, 2)  # noqa: E731
    return {
        "prompts": n,
        "avg_words": round(sum(p["words"] for p in profiles) / n, 1),
        "avg_specificity": round(sum(p["specificity"] for p in profiles) / n, 2),
        "anchored_ratio": ratio(lambda p: any([p["anchors"]["paths"], p["anchors"]["symbols"], p["anchors"]["error_text"]])),
        "vague_ratio": ratio(lambda p: p["vague"]),
        "delegation_ratio": ratio(lambda p: p["delegation"]),
        "acceptance_ratio": ratio(lambda p: p["acceptance"]),
        "pasted_code_ratio": ratio(lambda p: p["code_blocks"]),
        "repair_ratio": ratio(lambda p: p["intent"] == "repair"),
        "accept_ratio": ratio(lambda p: p["intent"] == "accept"),
        "intent_mix": dict(Counter(p["intent"] for p in profiles).most_common()),
        "mode_mix": dict(Counter(p["mode"] for p in profiles).most_common()),
        "top_signals": [s for s, _ in Counter(s for p in profiles for s in p["signals"]).most_common(5)],
    }


def notes_for(langs: Iterable[str]) -> Dict[str, str]:
    return {l: LANGUAGE_NOTES[l] for l in langs if l in LANGUAGE_NOTES}
