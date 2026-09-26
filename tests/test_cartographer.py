"""Run with:  python3 -m unittest discover -s tests -v

Codex and Cursor fixtures are synthetic (built here) because only Claude Code
data exists on the development machine. They follow the on-disk formats the
adapters document.
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("CARTOGRAPHER_HOME", tempfile.mkdtemp())

from cartographer import config, digest, hooks, lang, recap, store  # noqa: E402
from cartographer.adapters import claude_code, codex_cli, cursor, generic  # noqa: E402
from cartographer.adapters.base import ERROR, NOTE, PROMPT, REPLY, TOOL, Event, Session  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class ClaudeCodeTest(unittest.TestCase):
    def test_parses_prompts_tools_errors_branches_and_commands(self):
        tmp = tempfile.mkdtemp()
        lines = [
            {"type": "summary", "summary": "auto summary"},
            {"type": "custom-title", "customTitle": "Auth work"},
            {"type": "user", "timestamp": "2026-09-01T10:00:00Z", "cwd": "/repo", "gitBranch": "main",
             "message": {"role": "user", "content": [{"type": "text", "text": "<system-reminder>noise</system-reminder>Add login to src/app.ts"}]}},
            {"type": "assistant", "timestamp": "2026-09-01T10:01:00Z", "cwd": "/repo", "gitBranch": "main",
             "message": {"role": "assistant", "model": "claude-x", "content": [{"type": "text", "text": "On it."},
                         {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "/repo/src/app.ts"}}]}},
            {"type": "user", "timestamp": "2026-09-01T10:02:00Z", "cwd": "/repo", "gitBranch": "feature/login",
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "TypeError: x"}]}},
            {"type": "user", "isSidechain": True, "timestamp": "2026-09-01T10:03:00Z", "message": {"role": "user", "content": [{"type": "text", "text": "subagent chatter"}]}},
            {"type": "user", "timestamp": "2026-09-01T10:04:00Z", "cwd": "/repo", "gitBranch": "feature/login",
             "message": {"role": "user", "content": [{"type": "text", "text": "<command-name>/wrap</command-name><command-message>wrap</command-message><command-args></command-args>"}]}},
            {"type": "attachment", "timestamp": "2026-09-01T10:05:00Z",
             "rendered": [{"content": "<system-reminder>\nThe user sent a new message while you were working:\nmake it smaller\n\nThis is how Claude Code surfaces messages the user sends mid-turn.\n</system-reminder>"}]},
        ]
        path = write(os.path.join(tmp, "-repo", "abc.jsonl"), "\n".join(json.dumps(l) for l in lines))
        ad = claude_code.ClaudeCodeAdapter(projects_dir=tmp)
        s = ad.load_path(path)
        self.assertEqual([e.kind for e in s.events], [PROMPT, REPLY, TOOL, "branch", ERROR, NOTE, PROMPT])
        self.assertEqual((s.events[6].text, s.events[6].meta.get("mid_turn")), ("make it smaller", True))
        self.assertEqual(s.title, "Auth work")
        self.assertEqual(s.events[0].text, "Add login to src/app.ts")
        self.assertEqual(s.events[2].files, ["/repo/src/app.ts"])
        self.assertEqual(s.events[3].text, "feature/login")
        self.assertEqual(s.events[5].text, "ran /wrap")
        self.assertEqual(s.model, "claude-x")
        self.assertEqual(s.meta["subagent_events"], 1)
        self.assertEqual(ad.find("abc").id, "abc")


class CodexTest(unittest.TestCase):
    def test_current_format(self):
        tmp = tempfile.mkdtemp()
        sid = "11111111-2222-3333-4444-555555555555"
        lines = [
            {"timestamp": "2026-09-01T10:00:00Z", "type": "session_meta", "payload": {"id": sid, "cwd": "/repo", "cli_version": "0.5", "git": {"branch": "dev", "repository_url": "git@github.com:me/app.git"}}},
            {"timestamp": "2026-09-01T10:00:01Z", "type": "turn_context", "payload": {"cwd": "/repo", "model": "gpt-x"}},
            {"timestamp": "2026-09-01T10:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>Fix the failing test in tests/test_api.py"}]}},
            {"timestamp": "2026-09-01T10:00:03Z", "type": "response_item", "payload": {"type": "function_call", "name": "shell", "call_id": "c1", "arguments": json.dumps({"command": ["bash", "-lc", "pytest -q"]})}},
            {"timestamp": "2026-09-01T10:00:04Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": json.dumps({"output": "1 failed", "metadata": {"exit_code": 1}})}},
            {"timestamp": "2026-09-01T10:00:05Z", "type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch", "call_id": "c2", "input": "*** Begin Patch\n*** Update File: src/api.py\n@@\n-a\n+b\n*** End Patch"}},
            {"timestamp": "2026-09-01T10:00:06Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Fixed."}]}},
        ]
        write(os.path.join(tmp, "sessions", "2026", "09", "01", "rollout-2026-09-01T10-00-00-%s.jsonl" % sid), "\n".join(json.dumps(l) for l in lines))
        ad = codex_cli.CodexAdapter(home=tmp)
        refs = ad.list_sessions()
        self.assertEqual((refs[0].id, refs[0].cwd), (sid, "/repo"))
        s = ad.load(refs[0])
        self.assertEqual((s.branch, s.model), ("dev", "gpt-x"))
        self.assertEqual([e.kind for e in s.events], [PROMPT, TOOL, ERROR, TOOL, REPLY])
        self.assertEqual(s.events[0].text, "Fix the failing test in tests/test_api.py")
        self.assertEqual(s.events[1].text, "bash -lc pytest -q")
        self.assertEqual(s.events[3].files, ["src/api.py"])

    def test_legacy_format(self):
        tmp = tempfile.mkdtemp()
        lines = [
            {"id": "legacy-1", "timestamp": "2026-01-01T00:00:00Z", "instructions": "", "git": {"branch": "main"}},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello codex"}]},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]},
        ]
        path = write(os.path.join(tmp, "sessions", "rollout-legacy.jsonl"), "\n".join(json.dumps(l) for l in lines))
        s = codex_cli.CodexAdapter(home=tmp).load_path(path)
        self.assertEqual([e.kind for e in s.events], [PROMPT, REPLY])


class CursorTest(unittest.TestCase):
    def test_reads_composer_bubbles_and_workspace(self):
        tmp = tempfile.mkdtemp()
        gdir = os.path.join(tmp, "globalStorage")
        os.makedirs(gdir)
        con = sqlite3.connect(os.path.join(gdir, "state.vscdb"))
        con.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value BLOB)")
        cid = "comp-1"
        rows = [
            ("composerData:%s" % cid, {"composerId": cid, "name": "Style the navbar", "createdAt": 1756720000000, "lastUpdatedAt": 1756723600000,
                                       "fullConversationHeadersOnly": [{"bubbleId": "b%d" % i, "type": t} for i, t in ((1, 1), (2, 2), (3, 2), (4, 2))]}),
            ("bubbleId:%s:b1" % cid, {"type": 1, "text": "make the navbar sticky and cleaner", "createdAt": "2026-09-01T10:00:00Z", "context": {"fileSelections": [{"uri": {"path": "/ws/src/Nav.tsx"}}]}}),
            ("bubbleId:%s:b2" % cid, {"type": 2, "text": "", "toolFormerData": {"name": "edit_file", "params": json.dumps({"target_file": "src/Nav.tsx"}), "status": "completed"}}),
            ("bubbleId:%s:b3" % cid, {"type": 2, "text": "", "toolFormerData": {"name": "run_terminal_cmd", "params": json.dumps({"command": "npm test"}), "status": "error", "result": "{\"error\": \"exit 1\"}"}}),
            ("bubbleId:%s:b4" % cid, {"type": 2, "text": "Done, the navbar is sticky."}),
        ]
        con.executemany("INSERT INTO cursorDiskKV VALUES (?, ?)", [(k, json.dumps(v)) for k, v in rows])
        con.commit()
        con.close()
        ws = os.path.join(tmp, "workspaceStorage", "hash1")
        write(os.path.join(ws, "workspace.json"), json.dumps({"folder": "file:///ws"}))
        wcon = sqlite3.connect(os.path.join(ws, "state.vscdb"))
        wcon.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
        wcon.execute("INSERT INTO ItemTable VALUES (?, ?)", ("composer.composerData", json.dumps({"allComposers": [{"composerId": cid}]})))
        wcon.commit()
        wcon.close()
        ad = cursor.CursorAdapter(user_dir=tmp)
        self.assertTrue(ad.available())
        refs = ad.list_sessions()
        self.assertEqual((refs[0].cwd, refs[0].title), ("/ws", "Style the navbar"))
        s = ad.load(refs[0])
        self.assertEqual([e.kind for e in s.events], [PROMPT, TOOL, ERROR, REPLY])
        self.assertEqual(s.events[0].meta["attached"], ["/ws/src/Nav.tsx"])
        self.assertEqual(s.events[1].files, ["src/Nav.tsx"])
        self.assertEqual(ad.list_sessions(cwd="/elsewhere"), [])


class GenericTest(unittest.TestCase):
    def test_json_and_markdown(self):
        tmp = tempfile.mkdtemp()
        j = write(os.path.join(tmp, "chat.json"), json.dumps({"messages": [{"role": "user", "content": "build me a todo app in Svelte"}, {"role": "assistant", "content": "Sure", "tool_calls": [{"function": {"name": "write_file", "arguments": "{}"}}]}]}))
        self.assertEqual([e.kind for e in generic.GenericAdapter().load_path(j).events], [PROMPT, TOOL, REPLY])
        m = write(os.path.join(tmp, "chat.md"), "## User\nwhy is this slow?\n\n## Assistant\nBecause of N+1 queries.\n\n**User:**\nfix it\n")
        s = generic.GenericAdapter().load_path(m)
        self.assertEqual([e.kind for e in s.events], [PROMPT, REPLY, PROMPT])
        self.assertEqual(s.events[2].text, "fix it")


class LangTest(unittest.TestCase):
    def test_prompt_analysis(self):
        p = lang.analyze_prompt("Fix the TypeError in src/auth.ts line 42; it must keep the existing session cookie. Traceback: TypeError: undefined is not a function")
        self.assertEqual((p["intent"], p["mode"], p["specificity"]), ("fix", "imperative", 3))
        self.assertIn("src/auth.ts", p["anchors"]["paths"])
        self.assertTrue(p["anchors"]["error_text"])
        v = lang.analyze_prompt("make it look nicer and more modern, you decide the colors")
        self.assertEqual((v["intent"], v["specificity"]), ("design", 0))
        self.assertTrue(v["vague"] and v["delegation"])
        self.assertTrue(any("vague" in s for s in v["signals"]))
        self.assertEqual(lang.analyze_prompt("Why does the build fail on CI but not locally?")["mode"], "question")
        big = lang.analyze_prompt("build the whole app from scratch with auth, billing and an admin panel")
        self.assertEqual(big["scope"], "large")
        self.assertTrue(any("architecture" in s for s in big["signals"]))

    def test_repair_accept_and_file_anchors(self):
        rep = lang.analyze_prompt("no, I meant the other button. put it back in the header")
        self.assertEqual(rep["intent"], "repair")
        self.assertTrue(any("repair" in s for s in rep["signals"]))
        self.assertEqual(lang.analyze_prompt("yes go ahead")["intent"], "accept")
        self.assertEqual(lang.analyze_prompt("looks good, continue")["intent"], "accept")
        self.assertEqual(lang.analyze_prompt("ok now add a footer")["intent"], "build")
        self.assertEqual(lang.analyze_prompt("open this repo and let's refine the app")["intent"], "refactor")
        fx = lang.analyze_prompt("fix app.py, it crashes on empty input")
        self.assertEqual(fx["anchors"]["paths"], ["app.py"])
        self.assertFalse(any("guess where the bug" in s for s in fx["signals"]))
        self.assertEqual(lang.analyze_prompt("use version 3.9.6 and node.js")["anchors"], {"paths": [], "symbols": [], "line_refs": False, "urls": 0, "error_text": False})

    def test_language_detection(self):
        langs = lang.detect_languages(["src/main.rs", "src/lib.rs", "README.md"], ["python"], ["can you make the borrow checker happy"])
        self.assertEqual(langs[0]["lang"], "rust")
        self.assertIn("files", langs[0]["evidence"])
        self.assertEqual(set(lang.notes_for(["rust", "nope"])), {"rust"})
        fw = lang.detect_frameworks(["use Next.js app router and Supabase"], [])
        self.assertEqual([f["name"] for f in fw][:2], ["Next.js", "Supabase"])

    def test_aggregate(self):
        agg = lang.aggregate([lang.analyze_prompt("fix it"), lang.analyze_prompt("Add a /health route to server/app.py that should return 200"), lang.analyze_prompt("nope, the other file")])
        self.assertEqual((agg["prompts"], agg["repair_ratio"]), (3, 0.33))
        self.assertEqual(agg["anchored_ratio"], 0.33)


class RecapTest(unittest.TestCase):
    def moves(self, n=3, phase="A"):
        return [{"id": "m%d" % i, "t": i, "phase": phase, "you": "you did %d" % i, "happened": "it %d" % i, "outcome": "worked"} for i in range(1, n + 1)]

    def test_validate_and_normalize(self):
        r = {"title": "t", "goal": "g", "outcome": "o", "phases": [{"name": "A"}], "moves": self.moves()}
        r["moves"][2]["phase"] = "B"
        self.assertTrue(any("phase 'B'" in e for e in recap.validate(recap.normalize(r))))
        r["moves"][2]["phase"] = "A"
        r["moves"][1]["outcome"] = "meh"
        self.assertTrue(any("outcome" in e for e in recap.validate(recap.normalize(r))))
        r["moves"][1]["outcome"] = "broke"
        r["moves"][1]["mark"] = "dead_end"
        self.assertEqual(recap.validate(recap.normalize(r)), [])
        d = {"agent": "codex", "session_id": "abc", "started_at": "2026-09-01T10:00:00+00:00", "duration_min": 12.5,
             "languages": [{"lang": "go"}], "project": {"id": "github.com/me/app", "name": "app", "root": "/r", "remote": None, "kind": "git"}}
        n = recap.normalize(r, d)
        self.assertEqual((n["date"], n["languages"], n["project"]["id"]), ("2026-09-01", ["go"], "github.com/me/app"))
        d["agent"] = "claude-code"  # equals the schema example, and is still a real value to fill in
        self.assertEqual(recap.normalize(r, d)["agent"], "claude-code")

    def test_legacy_steps_become_moves(self):
        r = {"title": "t", "goal": "g", "outcome": "o", "phases": [{"name": "A"}],
             "steps": [{"id": "s1", "t": 0, "kind": "prompt", "phase": "A", "title": "Ask for a login page", "prompt": "add login", "detail": "vague"},
                       {"id": "s2", "t": 1, "kind": "artifact", "phase": "A", "title": "Login.tsx written", "files": ["src/Login.tsx"]},
                       {"id": "s3", "t": 2, "kind": "dead_end", "phase": "A", "title": "Cookie lost on refresh", "detail": "session not persisted"},
                       {"id": "s4", "t": 5, "kind": "prompt", "phase": "A", "title": "Ask to persist the session"},
                       {"id": "s5", "t": 6, "kind": "fix", "phase": "A", "title": "Store cookie server-side"},
                       {"id": "s6", "t": 9, "kind": "prompt", "phase": "A", "title": "Ask to ship it"}],
             "coaching": [{"focus": "prompt", "observation": "o", "suggestion": "s", "step": "s1"}]}
        n = recap.normalize(r)
        self.assertEqual(recap.validate(n), [])
        m1, m2, m3 = n["moves"]
        self.assertEqual((m1["id"], m1["you"], m1["prompt"]), ("s1", "Ask for a login page", "add login"))
        self.assertIn("Login.tsx written", m1["happened"])
        self.assertIn("Cookie lost on refresh", m1["happened"])
        self.assertEqual((m1["outcome"], m1["mark"], m1["files"]), ("wrong_way", "dead_end", ["src/Login.tsx"]))
        self.assertEqual(m1["response"], "Ask to persist the session")
        self.assertEqual((m2["outcome"], m2["mark"], m2["response"]), ("worked", "fix", "Ask to ship it"))
        self.assertEqual((m3["happened"], m3["response"]), ("Ask to ship it", ""))
        self.assertEqual(n["coaching"][0]["move"], "s1")

    def test_placeholders_are_filled_or_rejected(self):
        r = {"title": "Short session title", "goal": "g", "outcome": "o", "session_id": "…", "date": "YYYY-MM-DD", "duration_min": 0,
             "project": dict(recap.EXAMPLE["project"]), "phases": [{"name": "A"}], "moves": self.moves(),
             "coaching": [{"focus": "prompt", "observation": "o", "suggestion": "s", "move": "m9"}], "time_sinks": [{"what": "w", "minutes": "ten"}]}
        r["moves"][0]["t"] = "soon"
        r["moves"][1]["you"] = recap.EXAMPLE["moves"][0]["you"]
        d = {"session_id": "real-id", "title": "From digest", "started_at": "2026-09-02T09:00:00+00:00", "duration_min": 7, "project": {"id": "local:/x", "name": "x"}}
        n = recap.normalize(r, d)
        self.assertEqual((n["session_id"], n["date"], n["duration_min"], n["project"]["id"], n["title"]), ("real-id", "2026-09-02", 7, "local:/x", "From digest"))
        errs = recap.validate(n)
        for needle in ("t must be a number", "m9", "time_sinks[0]", "move m2: missing you"):
            self.assertTrue(any(needle in e for e in errs), needle)
        self.assertTrue(any("missing title" in e for e in recap.validate(recap.normalize(r))))


class VersionsAndAppraisalTest(unittest.TestCase):
    def test_goal_complete_and_appraisal_roundtrip(self):
        old = store.PROJECTS, store.SESSIONS
        tmp = tempfile.mkdtemp()
        store.PROJECTS, store.SESSIONS = os.path.join(tmp, "projects.json"), os.path.join(tmp, "sessions")
        try:
            entry = store.register_project("github.com/me/app", "app", "/r", None)
            self.assertIsNone(store.desired_for("github.com/me/app"))
            v = store.set_goal("app", "A CLI that maps sessions")
            self.assertEqual((v["name"], store.desired_for("github.com/me/app")), ("v1", "A CLI that maps sessions"))
            v = store.complete("app", "partial", "shipped without Cursor")
            self.assertEqual((v["name"], v["result"], v["actual"]), ("v1", "partial", "shipped without Cursor"))
            self.assertIsNone(store.desired_for("github.com/me/app"))  # v1 is closed; no open version
            self.assertEqual(store.set_goal("app", "next")["name"], "v2")
            self.assertEqual(store.get_version("app", "v1")["result"], "partial")
            with self.assertRaises(ValueError):
                store.complete("app", "meh")
            a = json.loads(json.dumps(recap.APPRAISAL_EXAMPLE))
            a["project"] = {"id": "github.com/me/app"}
            a["verdict"] = "It shipped without Cursor; the record shows the adapter was never run on real data."
            self.assertEqual(recap.validate_appraisal(a), [])
            bad = json.loads(json.dumps(a))
            bad["got_you_there"][0].pop("evidence")
            bad["verdict"] = "Great work all round."
            errs = recap.validate_appraisal(bad)
            self.assertTrue(any("evidence" in x for x in errs) and any("praise" in x for x in errs))
            path = store.save_appraisal(a, json.loads(json.dumps(config.DEFAULTS)))
            self.assertTrue(path.endswith("appraisal_v1.json"))
            self.assertEqual(store.load_recaps("app"), [])  # appraisals are not session maps
            self.assertEqual(store.load_appraisals(entry["slug"])[0]["version"], "v1")
            self.assertEqual(store.projects()["github.com/me/app"]["versions"][0]["appraisal"], path)
        finally:
            store.PROJECTS, store.SESSIONS = old

    def test_moves_need_evidence_shape_and_no_praise(self):
        moves = [{"id": "m%d" % i, "t": i, "phase": "A", "you": "you did %d" % i, "happened": "it %d" % i, "outcome": "worked", "evidence": ["prompt #%d" % i]} for i in range(1, 4)]
        r = {"title": "t", "goal": "g", "outcome": "o", "phases": [{"name": "A"}], "moves": moves}
        self.assertEqual(recap.validate(recap.normalize(r)), [])
        r["moves"][0]["evidence"] = "prompt #1"
        r["moves"][1]["consequence"] = "A great choice that shipped nicely."
        errs = recap.validate(recap.normalize(r))
        self.assertTrue(any("evidence must be a list" in x for x in errs))
        self.assertTrue(any("praise word" in x for x in errs))


class StoreAndConfigTest(unittest.TestCase):
    def test_redaction(self):
        text = "use sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789 and password: hunter2secret and ghp_" + "a" * 36
        out = store.redact_text(text)
        for secret in ("abcdefghijklmnopqrstuvwxyz", "hunter2secret", "a" * 36):
            self.assertNotIn(secret, out)
        self.assertIn("[redacted]", out)

    def test_wrapped_is_read_from_recap_filenames(self):
        old = store.SESSIONS
        store.SESSIONS = tempfile.mkdtemp()
        try:
            write(os.path.join(store.SESSIONS, "app", "2026-09-01_claude-code_abcdef12.json"), "{}")
            self.assertTrue(store.is_wrapped("claude-code", "abcdef12-3456-7890"))
            self.assertFalse(store.is_wrapped("codex", "abcdef12-3456-7890"))
            self.assertFalse(store.is_wrapped("claude-code", "ffffffff"))
            self.assertEqual(list(store.wrapped()), ["claude-code:abcdef12"])
        finally:
            store.SESSIONS = old

    def test_effective_config(self):
        cfg = json.loads(json.dumps(config.DEFAULTS))
        config.set_value(cfg, "profile.coding", "new")
        config.set_value(cfg, "profile.prompting", "new")
        eff = config.effective(cfg)
        self.assertEqual((eff["voice"], eff["focus"]), ("plain", "prompts"))
        config.set_value(cfg, "profile.coding", "advanced")
        config.set_value(cfg, "profile.prompting", "advanced")
        eff = config.effective(cfg)
        self.assertEqual((eff["voice"], eff["focus"]), ("native", "both"))
        with self.assertRaises(ValueError):
            config.set_value(cfg, "voice", "loud")

    def test_windows_shims_and_relpath(self):
        tmp = tempfile.mkdtemp()
        cmd, sh = hooks.write_shims(tmp, "C:\\Users\\o\\.cartographer\\app\\bin\\cartographer", python="C:\\Python312\\python.exe")
        with open(cmd, newline="") as fh:
            self.assertEqual(fh.read(), '@echo off\r\n"C:\\Python312\\python.exe" "C:\\Users\\o\\.cartographer\\app\\bin\\cartographer" %*\r\n')
        with open(sh) as fh:
            self.assertEqual(fh.read(), '#!/bin/sh\nexec "C:/Python312/python.exe" "C:/Users/o/.cartographer/app/bin/cartographer" "$@"\n')
        self.assertEqual(digest.relpath("C:\\Users\\o\\proj\\src\\app.py", "C:\\Users\\o\\proj"), "src/app.py")
        self.assertEqual(digest.relpath("/home/o/proj/src/app.py", "/home/o/proj/"), "src/app.py")
        self.assertEqual(digest.relpath("/elsewhere/x.py", "/home/o/proj"), "/elsewhere/x.py")
        self.assertTrue(hooks.command_prefix().startswith('"') and hooks.command_prefix().endswith('/bin/cartographer"'))

    def test_hook_in_manual_mode_only_records(self):
        cfg = json.loads(json.dumps(config.DEFAULTS))
        item = hooks.handle("claude-code", {"session_id": "abc", "cwd": "/repo", "transcript_path": "/t.jsonl", "hook_event_name": "SessionEnd"}, cfg)
        self.assertEqual((item["session_id"], item["cwd"], item["transcript"], item["event"]), ("abc", "/repo", "/t.jsonl", "SessionEnd"))
        self.assertNotIn("spawned", item)

    def test_cursor_newer_layout(self):
        # Cursor 2.x: titles in a composerHeaders table, workspaceIdentifier on each chat, workspaceUris on bubbles,
        # an empty-state placeholder, and no per-workspace composer list.
        tmp = tempfile.mkdtemp(); ws = os.path.join(tmp, "workspaceStorage", "abc123"); os.makedirs(ws); os.makedirs(os.path.join(tmp, "globalStorage"))
        with open(os.path.join(ws, "workspace.json"), "w") as fh:
            json.dump({"folder": "file:///Users/x/turn-timer"}, fh)
        con = sqlite3.connect(os.path.join(tmp, "globalStorage", "state.vscdb"))
        con.execute("CREATE TABLE cursorDiskKV (key TEXT, value BLOB)")
        con.execute("CREATE TABLE composerHeaders (composerId TEXT, data BLOB)")
        con.execute("INSERT INTO composerHeaders VALUES ('c1', ?)", (json.dumps({"name": "Turn timer parser"}),))
        rows = [("composerData:c1", {"createdAt": 1790389225516, "workspaceIdentifier": {"id": "abc123"}, "fullConversationHeadersOnly": [{"bubbleId": "b1", "type": 1}]}),
                ("composerData:c2", {"createdAt": 1790389225516, "workspaceIdentifier": {"id": "gone"}, "fullConversationHeadersOnly": [{"bubbleId": "b1", "type": 1}]}),
                ("composerData:empty-state-9", {}),
                ("bubbleId:c1:b1", {"type": 1, "text": "Build the parser first\nthen the table", "workspaceUris": []}),
                ("bubbleId:c2:b1", {"type": 1, "text": "what files are here?", "workspaceUris": ["file:///Users/x/other"]})]
        con.executemany("INSERT INTO cursorDiskKV VALUES (?, ?)", [(k, json.dumps(v)) for k, v in rows]); con.commit(); con.close()
        ad = cursor.CursorAdapter(user_dir=tmp)
        self.assertEqual([(r.id, r.cwd, r.title) for r in ad.list_sessions()],
                         [("c1", "/Users/x/turn-timer", "Turn timer parser"), ("c2", "/Users/x/other", "what files are here?")])
        self.assertEqual([r.id for r in ad.list_sessions(cwd="/Users/x/turn-timer")], ["c1"])
        dump = ad.dump()
        self.assertIn("table composerHeaders: 1 rows", dump)
        self.assertNotIn("Build the parser", dump)   # never message text

    def test_map_scores(self):
        from cartographer import render
        moves = [
            {"id": "m1", "t": 0, "outcome": "worked", "mark": "decision", "prompt": "Fix the KeyError in cartographer/store.py: load_recaps must skip appraisal_ files. Done when tests pass."},
            {"id": "m2", "t": 3, "outcome": "worked", "mark": "artifact"},                      # the agent's own work, governed by m1
            {"id": "m3", "t": 5, "outcome": "broke", "mark": "dead_end", "prompt": "make it nicer"},
            {"id": "m4", "t": 8, "outcome": "worked", "mark": "fix", "prompt": "no, I meant the dashboard, not the replay"},
        ]
        sc = render.score_moves([{"moves": moves}])
        self.assertEqual(sorted(sc), ["0:m1", "0:m2", "0:m3", "0:m4"])
        self.assertEqual(sc["0:m1"]["tier"], "achievement")           # worked, specific and anchored, not repaired
        self.assertTrue(sc["0:m1"]["anchored"] and sc["0:m1"]["specificity"] >= 2)
        self.assertEqual((sc["0:m2"]["tier"], sc["0:m2"]["prompt"]), ("achievement", 3))
        self.assertIn("prompt (m1)", sc["0:m2"]["why"])
        self.assertEqual(sc["0:m3"]["tier"], "setback")
        self.assertTrue(sc["0:m3"]["repaired"])                       # m4 opens with "no, I meant"
        self.assertEqual(sc["0:m4"]["tier"], "solid")                 # worked, but a bare repair prompt is not an achievement
        html = render.render_html([{"schema": "cartographer.session/v3", "moves": moves}], "t")
        self.assertIn('"scores"', html)
        self.assertIn('data-v="map"', html)

    def test_digest_from_session(self):
        t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
        s = Session(agent="generic", id="x", path="/tmp/x", cwd=None, events=[
            Event(t0, PROMPT, "Add a login page in src/Login.tsx using React"),
            Event(t0.replace(minute=1), TOOL, "src/Login.tsx", tool="Edit", files=["src/Login.tsx"]),
            Event(t0.replace(minute=2), ERROR, "TypeError", tool="Bash"),
            Event(t0.replace(minute=30), PROMPT, "now make it look nicer"),
        ])
        d = digest.build(s, json.loads(json.dumps(config.DEFAULTS)))
        self.assertEqual(d["stats"]["prompts"], 2)
        self.assertEqual(d["languages"][0]["lang"], "typescript")
        self.assertIn("React", [f["name"] for f in d["frameworks"]])
        self.assertIn("pause", [x["kind"] for x in d["timeline"]])
        self.assertEqual(d["duration_min"], 30.0)


class ServeTest(unittest.TestCase):
    def test_dashboard_routes_and_token(self):
        import http.client
        import threading
        from cartographer import serve
        srv = serve.make_server(0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def req(method, path, body=None, host=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
            if host:
                headers["Host"] = host
            c.request(method, path, body=body, headers=headers)
            r = c.getresponse()
            data = r.read().decode("utf-8")
            c.close()
            return r.status, r.getheader("Location"), data

        try:
            status, _, body = req("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn("Recent sessions", body)
            self.assertEqual(req("GET", "/", host="evil.example:80")[0], 403)
            self.assertEqual(req("POST", "/setup", "profile.coding=new")[0], 403)
            status, loc, _ = req("POST", "/setup", "token=%s&profile.coding=new&voice=plain&wrap.mode=manual" % serve.TOKEN)
            self.assertEqual((status, loc), (303, "/setup"))
            self.assertEqual(config.load()["profile"]["coding"], "new")
            with open(os.path.join(ROOT, "demo", "2026-09-24_claude-code_ca61170e.recap.json"), encoding="utf-8") as fh:
                store.save_recap(json.load(fh), config.load())
            slug = store.find_project("Cartographer")["slug"]
            status, _, body = req("GET", "/replay/" + slug)
            self.assertEqual(status, 200)
            self.assertIn("Replay the build", body)
            self.assertEqual(req("GET", "/replay/nope")[0], 404)
            self.assertIn("Open map", req("GET", "/")[2])
            status, _, body = req("GET", "/project/" + slug)
            self.assertEqual(status, 200)
            self.assertIn("The yardstick", body)
            status, loc, _ = req("POST", "/goal", "token=%s&project=%s&desired=A+CLI+that+maps+sessions" % (serve.TOKEN, slug))
            self.assertEqual((status, loc), (303, "/project/" + slug))
            self.assertEqual(store.desired_for("local:cartographer"), "A CLI that maps sessions")
            status, _, body = req("POST", "/complete", "token=%s&project=%s&result=shipped&actual=it+shipped" % (serve.TOKEN, slug))
            self.assertEqual(status, 200)
            self.assertIn("/complete", body)
            self.assertIn("Done meant: A CLI that maps sessions", body)
            self.assertTrue(store.get_version("local:cartographer", "v1")["completed_at"])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
