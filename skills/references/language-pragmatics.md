# How Cartographer reads prompts

Cartographer separates three things the mapping model would otherwise blur:

1. **The act** — what the prompt is doing: build, fix, refactor, explain, explore, test, config, deploy, design, review, plan, articulate, ask. Detected from verbs and phrases; corrected by the model from context.
2. **The anchoring** — what the prompt points at: file paths, symbols, line numbers, URLs, pasted error text, pasted code. Specificity is scored 0–3 from anchoring, constraints or a done-condition, and named languages/frameworks or examples. Vague wording with no anchor lowers it.
3. **The pragmatics** — how it's said: imperative, question, descriptive or mixed; hedges ("maybe", "I think"); delegation ("you decide"); scope words ("the whole app" vs "just"); aesthetic vocabulary ("cleaner", "pop", "snappier").

Each prompt gets a `read:` line in the brief with these signals plus concrete coaching opportunities, for example "fix request without the error text or a file". The digest also aggregates them into a per-session prompting profile (average specificity, anchored ratio, vague ratio, delegation ratio, done-condition ratio, intent mix).

## Language notes

`cartographer/lang.py` carries a note per language on how natural-language prompts about it tend to behave: what ambiguity hides in, what dead ends look like, what a good prompt includes. The brief includes the notes for the languages a session actually used (by files edited, code pasted, and names mentioned). They are priors; the mapping model's own knowledge applies on top. Add a language by adding an entry to `LANGUAGE_NOTES` and its extensions to `EXT_LANG`.

## Aptitude-aware output

The reader profile (`profile.coding`, `profile.prompting`) changes three things in the brief: the voice (plain vs technical), the coaching register per level, and the feedback focus (prompts, code or both). `voice: both` asks for a `plain` block on every step so the replay can toggle.
