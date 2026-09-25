"""Language detection and prompt pragmatics.

Two jobs:

1. Work out which programming languages and frameworks a session touched,
   from the files the agent edited, the code the user pasted, and the names
   the user used.
2. Read each prompt the way a linguist would: what act is it (build, fix,
   ask...), how specific is it, what does it anchor to, where is it vague,
   how much does it delegate. These are mechanical signals; the mapping
   model layers its own judgment on top of them.

`LANGUAGE_NOTES` is Cartographer's standing knowledge of how prompts about
each language tend to behave. The brief includes the notes for the
languages a session actually used, so retrospective maps of old sessions get
the same context as live ones.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

EXT_LANG = {
    "py": "python", "pyi": "python", "ipynb": "python",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript", "jsx": "javascript",
    "ts": "typescript", "tsx": "typescript", "mts": "typescript",
    "html": "html", "htm": "html", "css": "css", "scss": "css", "sass": "css", "less": "css",
    "vue": "vue", "svelte": "svelte", "astro": "astro",
    "rs": "rust", "go": "go", "java": "java", "kt": "kotlin", "kts": "kotlin", "swift": "swift",
    "m": "objective-c", "mm": "objective-c", "c": "c", "h": "c", "cpp": "cpp", "cc": "cpp", "hpp": "cpp",
    "cs": "csharp", "fs": "fsharp", "rb": "ruby", "php": "php", "ex": "elixir", "exs": "elixir",
    "erl": "erlang", "hs": "haskell", "scala": "scala", "clj": "clojure", "lua": "lua", "dart": "dart",
    "r": "r", "jl": "julia", "zig": "zig", "nim": "nim", "gd": "gdscript",
    "sql": "sql", "prisma": "prisma", "graphql": "graphql", "gql": "graphql", "proto": "protobuf",
    "sh": "shell", "bash": "shell", "zsh": "shell", "fish": "shell", "ps1": "powershell",
    "yml": "yaml", "yaml": "yaml", "toml": "toml", "json": "json", "xml": "xml", "ini": "config", "env": "config",
    "md": "markdown", "mdx": "markdown", "rst": "markdown", "txt": "text",
    "dockerfile": "docker", "tf": "terraform", "hcl": "terraform", "nix": "nix",
    "glsl": "shader", "wgsl": "shader", "hlsl": "shader", "frag": "shader", "vert": "shader",
    "sol": "solidity", "wasm": "wasm",
}
FENCE_LANG = {"js": "javascript", "ts": "typescript", "py": "python", "sh": "shell", "bash": "shell", "zsh": "shell",
              "shell": "shell", "console": "shell", "jsx": "javascript", "tsx": "typescript", "yml": "yaml",
              "rs": "rust", "golang": "go", "c++": "cpp", "c#": "csharp", "cs": "csharp", "objc": "objective-c",
              "html": "html", "css": "css", "sql": "sql", "json": "json", "text": "text", "txt": "text", "": "text"}
# Names people use for languages in prose. Order matters for display.
LANG_MENTIONS = {
    "python": r"\bpython\b|\bpy\b|\bpandas\b|\bfastapi\b|\bdjango\b|\bflask\b",
    "typescript": r"\btypescript\b|\bts\b(?!x)|\btsx\b",
    "javascript": r"\bjavascript\b|\bjs\b|\bnode(?:js)?\b|\bnpm\b",
    "html": r"\bhtml\b|\bmarkup\b", "css": r"\bcss\b|\btailwind\b|\bstyles?heet\b",
    "rust": r"\brust\b|\bcargo\b|\bborrow checker\b", "go": r"\bgolang\b|\bgo (?:module|routine|func)\b|\bgoroutine\b",
    "swift": r"\bswift(?:ui)?\b|\bxcode\b|\bios app\b", "kotlin": r"\bkotlin\b|\bandroid\b|\bjetpack\b",
    "java": r"\bjava\b(?!script)|\bspring\b|\bmaven\b|\bgradle\b", "csharp": r"\bc#\b|\bcsharp\b|\b\.net\b|\bunity\b",
    "cpp": r"\bc\+\+\b|\bcpp\b", "c": r"\bc language\b|\bansi c\b", "ruby": r"\bruby\b|\brails\b",
    "php": r"\bphp\b|\blaravel\b", "sql": r"\bsql\b|\bpostgres(?:ql)?\b|\bsqlite\b|\bmysql\b|\bquery\b.*\btable\b",
    "shell": r"\bbash\b|\bshell script\b|\bzsh\b", "gdscript": r"\bgodot\b|\bgdscript\b",
    "dart": r"\bflutter\b|\bdart\b", "elixir": r"\belixir\b|\bphoenix\b", "lua": r"\blua\b|\bl[öo]ve2d\b|\broblox\b",
    "shader": r"\bshader\b|\bglsl\b|\bwgsl\b", "yaml": r"\byaml\b|\bgithub actions\b|\bworkflow file\b",
    "docker": r"\bdocker(?:file)?\b|\bcontainer\b", "terraform": r"\bterraform\b",
}
FRAMEWORKS = [
    (r"\bnext\.?js\b|\bnext app\b|\bapp router\b", "Next.js", "typescript"),
    (r"\breact(?:\.js)?\b|\bjsx\b|\buseState\b|\bcomponent\b", "React", "javascript"),
    (r"\bvue\b|\bnuxt\b", "Vue", "javascript"), (r"\bsvelte(?:kit)?\b", "Svelte", "javascript"),
    (r"\bexpress\b", "Express", "javascript"), (r"\bvite\b", "Vite", "javascript"),
    (r"\btailwind\b", "Tailwind", "css"), (r"\bthree\.?js\b|\bwebgl\b", "Three.js / WebGL", "javascript"),
    (r"\bphaser\b", "Phaser", "javascript"), (r"\bexpo\b|\breact native\b", "React Native", "typescript"),
    (r"\bdjango\b", "Django", "python"), (r"\bflask\b", "Flask", "python"), (r"\bfastapi\b", "FastAPI", "python"),
    (r"\bpandas\b|\bnumpy\b", "pandas / NumPy", "python"), (r"\bpytorch\b|\btorch\b", "PyTorch", "python"),
    (r"\bstreamlit\b", "Streamlit", "python"), (r"\bpygame\b", "Pygame", "python"),
    (r"\brails\b", "Rails", "ruby"), (r"\blaravel\b", "Laravel", "php"), (r"\bspring boot\b", "Spring Boot", "java"),
    (r"\bswiftui\b", "SwiftUI", "swift"), (r"\buikit\b", "UIKit", "swift"), (r"\bjetpack compose\b", "Compose", "kotlin"),
    (r"\bflutter\b", "Flutter", "dart"), (r"\bunity\b", "Unity", "csharp"), (r"\bgodot\b", "Godot", "gdscript"),
    (r"\bunreal\b", "Unreal", "cpp"), (r"\bbevy\b", "Bevy", "rust"), (r"\baxum\b|\btokio\b", "Axum / Tokio", "rust"),
    (r"\bsupabase\b", "Supabase", "sql"), (r"\bfirebase\b", "Firebase", "javascript"),
    (r"\bprisma\b", "Prisma", "typescript"), (r"\bdrizzle\b", "Drizzle", "typescript"),
    (r"\bpostgres(?:ql)?\b", "Postgres", "sql"), (r"\bsqlite\b", "SQLite", "sql"), (r"\bredis\b", "Redis", "config"),
    (r"\bdocker\b", "Docker", "docker"), (r"\bgithub actions\b", "GitHub Actions", "yaml"),
    (r"\bvercel\b", "Vercel", "config"), (r"\bnetlify\b", "Netlify", "config"), (r"\bfly\.io\b|\bflyctl\b", "Fly.io", "config"),
    (r"\bstripe\b", "Stripe", "javascript"), (r"\bauth0\b|\bclerk\b|\bnextauth\b", "Auth provider", "typescript"),
    (r"\bopenai\b|\banthropic\b|\bclaude api\b|\bllm\b", "LLM API", "python"),
    (r"\bmcp\b|\bmodel context protocol\b", "MCP", "typescript"), (r"\belectron\b|\btauri\b", "Desktop shell", "typescript"),
]

# Standing knowledge: how natural-language prompts behave per language. Short,
# concrete, and written for the mapping model, which adds its own judgment.
LANGUAGE_NOTES: Dict[str, str] = {
    "python": ("Prompts are usually task-first and terse ('parse this CSV', 'add a CLI flag'). Ambiguity hides in "
               "environment, not syntax: which interpreter, venv, and package manager. Dead ends cluster around "
               "dependency and import errors and around silent type mismatches (None, str vs bytes). 'Pythonic' and "
               "'clean' are requests for idiom, not behavior. Good prompts name the Python version and how it's run."),
    "javascript": ("Prompts often describe behavior in UI terms ('when I click', 'it should update'). Words like "
                   "'reactive', 'state', 'async' carry framework-specific meaning; the agent picks a framework if the "
                   "user doesn't. Dead ends: tooling and bundler config, async ordering, undefined-is-not-a-function, "
                   "dependency version churn. Good prompts name the runtime (browser vs Node) and the framework."),
    "typescript": ("Same as JavaScript, plus a second conversation with the type checker. 'Fix the types' and 'make it "
                   "compile' loops are common; users often accept `any` under time pressure, which is a decision worth "
                   "mapping. Good prompts say whether strictness matters and whether types are documentation or "
                   "safety."),
    "html": ("Prompts are visual and comparative ('like this site', 'more modern', 'make it pop') and often come with "
             "screenshots or links. The agent guesses at aesthetics; the user corrects by feel. Dead ends are layout "
             "fights (centering, overflow, responsive breakpoints). Good prompts give a reference, a breakpoint list, "
             "and the one thing that must not move."),
    "css": ("Aesthetic vocabulary ('cleaner', 'breathing room', 'pop') maps poorly onto properties; expect several "
            "rounds of adjustment. Specificity and cascade collisions are the classic silent dead end. Good prompts "
            "name the component, the states (hover, focus, mobile) and any design tokens."),
    "rust": ("Prompts are precise but the compiler drives the session: 'make it compile' and borrow-checker loops "
             "dominate, and the agent may reach for `.clone()` or `unwrap()` to escape. Those escapes are decisions. "
             "Good prompts state ownership intent (who owns what, is it shared, is it async) and the crate set."),
    "go": ("Prompts tend to be about structure and concurrency (goroutines, channels, context). Errors are explicit, "
           "so dead ends are usually design (package layout, interfaces) rather than syntax. Good prompts name the "
           "module path and how the binary is run."),
    "swift": ("Sessions are shaped by Xcode: build errors, previews, signing, simulator state. Prompts mix UI intent "
              "with platform constraints ('on iPad', 'in the share sheet'). Dead ends: SwiftUI state ownership "
              "(@State vs @Binding vs observable), and toolchain issues the agent can't see. Good prompts include the "
              "target OS version and the exact error text."),
    "kotlin": ("Android sessions carry Gradle and SDK-version friction; much of the time goes to configuration, not "
               "logic. Prompts are UI-first (Compose). Good prompts pin the Gradle/AGP versions and the min SDK."),
    "java": ("Prompts are usually structural (services, layers, annotations). Build tools (Maven/Gradle) and framework "
             "magic (Spring) create dead ends that look like code bugs. Good prompts name the framework version and "
             "how the app is run."),
    "csharp": ("Unity sessions are about lifecycle (Update, coroutines, prefabs) and editor state the agent cannot "
               "see; .NET web sessions are about DI and configuration. Prompts often describe game feel ('snappier', "
               "'floaty'), which needs numbers to converge. Good prompts give the Unity/.NET version and the scene "
               "or component involved."),
    "gdscript": ("Godot prompts describe scenes and signals; the node tree is the shared mental model, so prompts that "
                 "name nodes and paths converge fast, and ones that don't produce guesses. Editor-side setup is a "
                 "recurring dead end because the agent can only touch files."),
    "sql": ("Prompts are declarative ('get all users who...') and the risk is semantic, not syntactic: joins that "
            "multiply rows, NULL handling, timezone drift. Dead ends: migrations that don't match the ORM, and "
            "permissions. Good prompts include the schema or a sample row and the expected result shape."),
    "shell": ("Prompts are imperative one-liners. Danger is in scope ('clean up' can delete), quoting and portability "
              "(macOS vs Linux tools). Good prompts name the OS and what must not be touched."),
    "yaml": ("CI and infra prompts are outcome-shaped ('make the tests run on push'); the cost is the feedback loop, "
             "since each try runs remotely. Dead ends: indentation, secrets, permissions. Good prompts paste the "
             "failing job log."),
    "docker": ("Prompts are about getting something to run somewhere else. Dead ends: base image mismatches, build "
               "context, ports and volumes. Good prompts give the target platform and the exact run command."),
    "dart": ("Flutter prompts are widget-tree prompts; state management choice is usually implicit and worth mapping "
             "as a decision. Dead ends: platform channels and build setup."),
    "shader": ("Prompts are visual and physical ('glowy', 'wobble', 'water'). Iteration is by eye, so screenshots and "
               "numeric parameters are the useful anchors. Dead ends: coordinate spaces and precision."),
    "markdown": "Docs prompts are about audience and tone; ambiguity is 'who is this for'. Good prompts say who reads it.",
    "config": "Configuration prompts are about environments; ask which machine/stage before mapping a dead end as a bug.",
}

INTENT_WORDS = {
    "build": ["build", "rebuild", "built", "create", "make", "add", "implement", "write", "generate", "scaffold", "set up", "new", "start", "prototype", "app", "feature"],
    "fix": ["fix", "bug", "broken", "doesn't work", "does not work", "not working", "error", "crash", "fails", "failing", "wrong", "isn't", "won't"],
    "refactor": ["refactor", "clean", "reorganize", "simplify", "rename", "extract", "move", "split", "dedupe", "tidy", "restructure"],
    "explain": ["explain", "what does", "why does", "how does", "walk me through", "understand", "what is", "meaning"],
    "explore": ["look at", "find", "where is", "search", "check", "investigate", "inspect", "list", "show me", "read", "look into"],
    "test": ["test", "tests", "coverage", "spec", "assert", "unit", "e2e"],
    "config": ["configure the", "install the", "dependency", "dependencies", "env var", "environment variable", "settings file", "dotfile", "package.json", "requirements.txt"],
    "deploy": ["deploy", "ship", "release", "publish", "docker", "ci", "pipeline", "production", "host"],
    "design": ["design", "layout", "style", "css", "look", "ui", "ux", "font", "color", "colour", "responsive", "animation", "theme", "polish", "nicer", "prettier", "modern", "spacing"],
    "review": ["review", "audit", "critique", "check for", "security", "lint", "feedback on"],
    "plan": ["plan", "architecture", "approach", "options", "tradeoff", "trade-off", "should we", "think through", "spec", "outline", "roadmap"],
    "articulate": ["articulate", "help me describe", "put into words", "pitch", "explain my idea", "concept"],
}
VAGUE = ["make it better", "doesn't work", "does not work", "not working", "fix it", "clean up", "nicer", "make it pop",
         "something like", "somehow", "and stuff", "kind of", "sort of", "whatever", "just make", "look good", "look nice",
         "modern", "sleek", "professional", "cool", "better", "improve it", "it's broken", "weird", "off", "janky", "buggy"]
DELEGATE = ["you decide", "your call", "whatever you think", "use your judgment", "use your judgement", "up to you",
            "however you want", "pick the best", "do what makes sense", "you choose", "surprise me"]
HEDGES = ["maybe", "i think", "perhaps", "possibly", "might", "not sure", "i guess", "probably", "could we"]
LARGE = ["entire", "whole", "full", "complete", "from scratch", "end to end", "end-to-end", "all of", "everything", "the app", "the game", "mvp"]
SMALL = ["small", "quick", "tiny", "just", "one line", "minor", "little", "only"]
ACCEPT = ["should return", "should show", "should display", "expect", "so that", "until", "passes", "works when", "must",
          "output should", "test passes", "acceptance", "when i", "then it", "verify"]
CONSTRAINT = ["must", "should", "never", "only", "don't", "do not", "without", "keep", "avoid", "make sure", "always", "instead of", "not allowed"]
EXAMPLE = ["for example", "e.g.", "like this", "example:", "here's an example", "such as", "similar to"]
QUESTION_START = ("what", "why", "how", "where", "when", "which", "who", "can", "could", "should", "is", "are", "does", "do", "would", "will", "any")
VERBS = ("add", "build", "create", "make", "fix", "write", "implement", "refactor", "change", "update", "remove", "delete", "move",
         "rename", "run", "test", "check", "look", "find", "explain", "show", "generate", "set", "install", "deploy", "design",
         "convert", "turn", "give", "help", "let's", "lets", "please", "go", "try", "use", "replace", "extract", "clean", "rewrite",
         "review", "plan", "start", "continue", "keep", "stop", "open", "read", "search", "list", "describe", "draft", "put")
SYMBOL_RE = re.compile(r"`[^`\n]{2,60}`|\b[a-zA-Z_]\w*\(\)|\b[a-z]+[A-Z]\w*[A-Z]?\w*\b|\b[a-z]+_[a-z_]+\b|\b\w+\.\w+\.\w+\b")
LINE_RE = re.compile(r"\bline\s+\d+|:\d+(?::\d+)?\b")
URL_RE = re.compile(r"https?://\S+")
ERROR_RE = re.compile(r"Traceback|Error:|error\[E\d+\]|Exception|TypeError|ReferenceError|SyntaxError|panic|Segmentation|exit code|ENOENT|ECONN|undefined is not", re.I)
PATH_RE = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8})(?![\w/])")


INTENT_PRIORITY = ("fix", "design", "refactor", "test", "deploy", "config", "review", "plan", "articulate", "explain", "explore", "build")


def _count(text: str, phrases: Iterable[str]) -> List[str]:
    """Phrases present in text, tolerant of simple inflections (color/colors, look/looking)."""
    t = text.lower()
    out = []
    for p in phrases:
        pat = r"(?<![a-z])" + re.escape(p.strip()) + r"(?:s|es|ed|ing)?(?![a-z])"
        if re.search(pat, t):
            out.append(p)
    return out


def lang_of_file(path: str) -> Optional[str]:
    base = os.path.basename(path).lower()
    if base == "dockerfile" or base.startswith("dockerfile."):
        return "docker"
    if base in ("makefile", "cmakelists.txt"):
        return "config"
    if base.startswith(".env"):
        return "config"
    ext = base.rsplit(".", 1)[-1] if "." in base else ""
    return EXT_LANG.get(ext)


def detect_languages(files: Iterable[str], fences: Iterable[str], texts: Iterable[str]) -> List[Dict[str, Any]]:
    """Rank languages by evidence. Files count most, then pasted code, then names in prose."""
    score: Counter = Counter()
    sources: Dict[str, set] = {}

    def add(lang, n, src):
        if not lang:
            return
        score[lang] += n
        sources.setdefault(lang, set()).add(src)

    for f in files:
        add(lang_of_file(f), 3, "files")
    for tag in fences:
        lang = FENCE_LANG.get(tag, tag) if tag else "text"
        if lang and lang != "text":
            add(lang if lang in LANGUAGE_NOTES or lang in EXT_LANG.values() else None, 2, "pasted code")
    joined = "\n".join(t.lower() for t in texts)
    for lang, pattern in LANG_MENTIONS.items():
        hits = len(re.findall(pattern, joined, flags=re.I))
        if hits:
            add(lang, min(hits, 5), "mentions")
    out = []
    for lang, n in score.most_common():
        if lang in ("text", "markdown", "json") and len(score) > 1:
            continue
        out.append({"lang": lang, "score": n, "evidence": sorted(sources.get(lang, []))})
    return out


def detect_frameworks(texts: Iterable[str], files: Iterable[str]) -> List[Dict[str, str]]:
    joined = ("\n".join(texts) + "\n" + "\n".join(files)).lower()
    out, seen = [], set()
    for pattern, name, lang in FRAMEWORKS:
        if name not in seen and re.search(pattern, joined, flags=re.I):
            seen.add(name)
            out.append({"name": name, "lang": lang})
    return out


def analyze_prompt(text: str) -> Dict[str, Any]:
    """Mechanical reading of one prompt. Everything here is a signal, not a verdict."""
    raw = text or ""
    lower = raw.lower().strip()
    first = re.sub(r"^[^a-z]+", "", lower.split("\n", 1)[0])[:40]
    words = len(raw.split())
    fences = re.findall(r"```([A-Za-z0-9_+#.-]*)", raw)
    prose = re.sub(r"```.*?```", " ", raw, flags=re.S)
    paths = [p for p in PATH_RE.findall(prose) if not p.startswith("http")]
    symbols = [s for s in SYMBOL_RE.findall(prose) if len(s) > 2][:12]
    urls = len(URL_RE.findall(prose))
    has_error = bool(ERROR_RE.search(raw))
    lines = bool(LINE_RE.search(prose))

    scores = {intent: len(_count(prose, phrases)) for intent, phrases in INTENT_WORDS.items()}
    if has_error:
        scores["fix"] += 2
    best = max(scores.items(), key=lambda kv: (kv[1], -INTENT_PRIORITY.index(kv[0])))
    is_question = prose.strip().endswith("?") or first.split(" ")[0] in QUESTION_START
    intent = best[0] if best[1] > 0 else ("ask" if is_question else "other")
    if is_question and intent in ("other", "explore") and scores["explain"] == 0:
        intent = "ask"

    starts_verb = first.split(" ")[0] in VERBS if first else False
    if starts_verb or "please" in lower[:60]:
        mode = "imperative"
    elif is_question:
        mode = "question"
    elif any(w in lower for w in ("i want", "i'd like", "i need", "it should", "we need", "the goal", "idea")):
        mode = "descriptive"
    else:
        mode = "mixed"

    constraints = _count(prose, CONSTRAINT)
    acceptance = _count(prose, ACCEPT)
    vague = _count(prose, VAGUE)
    delegate = _count(prose, DELEGATE)
    hedges = _count(prose, HEDGES)
    examples = _count(prose, EXAMPLE)
    langs = [lang for lang, pat in LANG_MENTIONS.items() if re.search(pat, prose, flags=re.I)]
    fws = [f["name"] for f in detect_frameworks([prose], [])]

    anchored = bool(paths or symbols or lines or urls or has_error)
    specificity = 0
    specificity += 1 if anchored else 0
    specificity += 1 if (constraints or acceptance) else 0
    specificity += 1 if (fences or examples or langs or fws) else 0
    if vague and not anchored:
        specificity = max(0, specificity - 1)

    if _count(prose, LARGE):
        scope = "large"
    elif _count(prose, SMALL) or words < 12:
        scope = "small"
    else:
        scope = "medium"

    signals = []  # concrete coaching opportunities, phrased for the mapping model
    if intent == "fix" and not has_error and not paths:
        signals.append("fix request without the error text or a file: the agent had to guess where the bug lives")
    if vague and not anchored:
        signals.append("aesthetic or vague wording (%s) with nothing to anchor it" % ", ".join(vague[:3]))
    if scope == "large" and specificity <= 1:
        signals.append("large scope with little detail: the agent chose the architecture")
    if delegate:
        signals.append("explicit delegation (%s): decisions moved to the agent" % delegate[0])
    if intent == "build" and not acceptance and words > 20:
        signals.append("no stated done-condition: success was judged by feel")
    if fences and intent in ("fix", "explain"):
        signals.append("pasted code: strong anchor, good practice")
    if paths and (constraints or acceptance):
        signals.append("anchored and constrained: a high-precision prompt")

    return {
        "words": words, "mode": mode, "intent": intent, "scope": scope, "specificity": specificity,
        "anchors": {"paths": paths[:8], "symbols": symbols[:8], "line_refs": lines, "urls": urls, "error_text": has_error},
        "constraints": len(constraints), "acceptance": bool(acceptance), "examples": bool(examples),
        "vague": vague[:4], "delegation": bool(delegate), "hedges": len(hedges),
        "code_blocks": [FENCE_LANG.get(f.lower(), f.lower()) or "text" for f in fences],
        "languages": langs, "frameworks": fws, "signals": signals,
    }


def aggregate(profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(profiles)
    if not n:
        return {"prompts": 0}
    intents = Counter(p["intent"] for p in profiles)
    modes = Counter(p["mode"] for p in profiles)
    signals = Counter(s for p in profiles for s in p["signals"])
    return {
        "prompts": n,
        "avg_words": round(sum(p["words"] for p in profiles) / n, 1),
        "avg_specificity": round(sum(p["specificity"] for p in profiles) / n, 2),
        "anchored_ratio": round(sum(1 for p in profiles if any([p["anchors"]["paths"], p["anchors"]["symbols"], p["anchors"]["error_text"]])) / n, 2),
        "vague_ratio": round(sum(1 for p in profiles if p["vague"]) / n, 2),
        "delegation_ratio": round(sum(1 for p in profiles if p["delegation"]) / n, 2),
        "acceptance_ratio": round(sum(1 for p in profiles if p["acceptance"]) / n, 2),
        "pasted_code_ratio": round(sum(1 for p in profiles if p["code_blocks"]) / n, 2),
        "intent_mix": dict(intents.most_common()),
        "mode_mix": dict(modes.most_common()),
        "top_signals": [s for s, _ in signals.most_common(5)],
    }


def notes_for(langs: Iterable[str]) -> Dict[str, str]:
    return {l: LANGUAGE_NOTES[l] for l in langs if l in LANGUAGE_NOTES}
