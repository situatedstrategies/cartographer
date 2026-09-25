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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cartographer import config, digest, lang, recap, store  # noqa: E402
from cartographer.adapters import claude_code, codex_cli, cursor, generic  # noqa: E402
from cartographer.adapters.base import ERROR, PROMPT, REPLY, TOOL, SessionRef  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class ClaudeCodeTest(unittest.TestCase):
    def test_parses_prompts_tools_errors_and_branches(self):
        tmp = tempfile.mkdtemp()
        lines = [
            {"type": "custom-title", "customTitle": "Auth work"},
            {"type": "user", "timestamp": "2026-09-01T10:00:00Z", "cwd": "/repo", "gitBranch": "main",
             "message": {"role": "user", "content": [{"type": "text", "text": "<system-reminder>noise</system-reminder>Add login to src/app.ts"}]}},
            {"type": "assistant", "timestamp": "2026-09-01T10:01:00Z", "cwd": "/repo", "gitBranch": "main",
             "message": {"role": "assistant", "model": "claude-x", "content": [{"type": "text", "text": "On it."},
                         {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "/repo/src/app.ts"}}]}},
            {"type": "user", "timestamp": "2026-09-01T10:02:00Z", "cwd": "/repo", "gitBranch": "feature/login",
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "TypeError: x"}]}},
            {"type": "user", "isSidechain": True, "timestamp": "2026-09-01T10:03:00Z", "message": {"role": "user", "content": [{"type": "text", "text": "subagent chatter"}]}},
        ]
        path = write(os.path.join(tmp, "-repo", "abc.jsonl"), "\n".join(json.dumps(l) for l in lines))
        ad = claude_code.ClaudeCodeAdapter(projects_dir=tmp)
        s = ad.load_path(path)
        kinds = [e.kind for e in s.events]
        self.assertEqual(kinds, [PROMPT, REPLY, TOOL, "branch", ERROR])
        self.assertEqual(s.events[0].text, "Add login to src/app.ts")
        self.assertEqual(s.events[2].files, ["/repo/src/app.ts"])
        self.assertEqual(s.model, "claude-x")
        self.assertEqual(s.meta["subagent_events"], 1)
        self.assertEqual(s.events[3].text, "feature/login")
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
        path = write(os.path.join(tmp, "sessions", "2026", "09", "01", "rollout-2026-09-01T10-00-00-%s.jsonl" % sid), "\n".join(json.dumps(l) for l in lines))
        ad = codex_cli.CodexAdapter(home=tmp)
        refs = ad.list_sessions()
        self.assertEqual(refs[0].id, sid)
        self.assertEqual(refs[0].cwd, "/repo")
        s = ad.load(refs[0])
        self.assertEqual(s.branch, "dev")
        self.assertEqual(s.model, "gpt-x")
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
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:%s" % cid, json.dumps({
            "composerId": cid, "name": "Style the navbar", "createdAt": 1756720000000, "lastUpdatedAt": 1756723600000,
            "fullConversationHeadersOnly": [{"bubbleId": "b1", "type": 1}, {"bubbleId": "b2", "type": 2}, {"bubbleId": "b3", "type": 2}, {"bubbleId": "b4", "type": 2}]})))
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b1" % cid, json.dumps({"type": 1, "text": "make the navbar sticky and cleaner", "createdAt": "2026-09-01T10:00:00Z",
                                                                                                    "context": {"fileSelections": [{"uri": {"path": "/ws/src/Nav.tsx"}}]}})))
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b2" % cid, json.dumps({"type": 2, "text": "", "toolFormerData": {"name": "edit_file", "params": json.dumps({"target_file": "src/Nav.tsx"}), "status": "completed"}})))
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b3" % cid, json.dumps({"type": 2, "text": "", "toolFormerData": {"name": "run_terminal_cmd", "params": json.dumps({"command": "npm test"}), "status": "error", "result": "{\"error\": \"exit 1\"}"}})))
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b4" % cid, json.dumps({"type": 2, "text": "Done, the navbar is sticky."})))
        con.commit()
        con.close()
        ws = os.path.join(tmp, "workspaceStorage", "hash1")
        os.makedirs(ws)
        write(os.path.join(ws, "workspace.json"), json.dumps({"folder": "file:///ws"}))
        wcon = sqlite3.connect(os.path.join(ws, "state.vscdb"))
        wcon.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
        wcon.execute("INSERT INTO ItemTable VALUES (?, ?)", ("composer.composerData", json.dumps({"allComposers": [{"composerId": cid}]})))
        wcon.commit()
        wcon.close()
        ad = cursor.CursorAdapter(user_dir=tmp)
        self.assertTrue(ad.available())
        refs = ad.list_sessions()
        self.assertEqual(refs[0].cwd, "/ws")
        self.assertEqual(refs[0].title, "Style the navbar")
        s = ad.load(refs[0])
        self.assertEqual([e.kind for e in s.events], [PROMPT, TOOL, ERROR, REPLY])
        self.assertEqual(s.events[0].meta["attached"], ["/ws/src/Nav.tsx"])
        self.assertEqual(s.events[1].files, ["src/Nav.tsx"])
        self.assertEqual(ad.list_sessions(cwd="/elsewhere"), [])


class GenericTest(unittest.TestCase):
    def test_json_and_markdown(self):
        tmp = tempfile.mkdtemp()
        j = write(os.path.join(tmp, "chat.json"), json.dumps({"messages": [{"role": "user", "content": "build me a todo app in Svelte"}, {"role": "assistant", "content": "Sure", "tool_calls": [{"function": {"name": "write_file", "arguments": "{}"}}]}]}))
        s = generic.GenericAdapter().load_path(j)
        self.assertEqual([e.kind for e in s.events], [PROMPT, TOOL, REPLY])
        m = write(os.path.join(tmp, "chat.md"), "## User\nwhy is this slow?\n\n## Assistant\nBecause of N+1 queries.\n\n**User:**\nfix it\n")
        s = generic.GenericAdapter().load_path(m)
        self.assertEqual([e.kind for e in s.events], [PROMPT, REPLY, PROMPT])
        self.assertEqual(s.events[2].text, "fix it")


class LangTest(unittest.TestCase):
    def test_prompt_analysis(self):
        p = lang.analyze_prompt("Fix the TypeError in src/auth.ts line 42; it must keep the existing session cookie. Traceback: TypeError: undefined is not a function")
        self.assertEqual(p["intent"], "fix")
        self.assertEqual(p["mode"], "imperative")
        self.assertIn("src/auth.ts", p["anchors"]["paths"])
        self.assertTrue(p["anchors"]["error_text"])
        self.assertEqual(p["specificity"], 3)
        v = lang.analyze_prompt("make it look nicer and more modern, you decide the colors")
        self.assertEqual(v["intent"], "design")
        self.assertTrue(v["vague"])
        self.assertTrue(v["delegation"])
        self.assertEqual(v["specificity"], 0)
        self.assertTrue(any("vague" in s for s in v["signals"]))
        q = lang.analyze_prompt("Why does the build fail on CI but not locally?")
        self.assertEqual(q["mode"], "question")
        big = lang.analyze_prompt("build the whole app from scratch with auth, billing and an admin panel")
        self.assertEqual(big["scope"], "large")
        self.assertTrue(any("architecture" in s for s in big["signals"]))

    def test_language_detection(self):
        langs = lang.detect_languages(["src/main.rs", "src/lib.rs", "README.md"], ["python"], ["can you make the borrow checker happy"])
        self.assertEqual(langs[0]["lang"], "rust")
        self.assertIn("files", langs[0]["evidence"])
        self.assertTrue(lang.notes_for(["rust", "nope"]).keys() == {"rust"})
        fw = lang.detect_frameworks(["use Next.js app router and Supabase"], [])
        self.assertEqual([f["name"] for f in fw][:2], ["Next.js", "Supabase"])

    def test_aggregate(self):
        agg = lang.aggregate([lang.analyze_prompt("fix it"), lang.analyze_prompt("Add a /health route to server/app.py that should return 200")])
        self.assertEqual(agg["prompts"], 2)
        self.assertEqual(agg["anchored_ratio"], 0.5)


class RecapAndStoreTest(unittest.TestCase):
    def test_validate_and_normalize(self):
        r = {"title": "t", "goal": "g", "outcome": "o", "phases": [{"name": "A"}],
             "steps": [{"id": "s1", "kind": "prompt", "title": "x", "phase": "A"}, {"id": "s2", "kind": "dead_end", "title": "y", "phase": "A", "links": [{"to": "s3", "rel": "reverted"}]},
                       {"id": "s3", "kind": "fix", "title": "z", "phase": "B"}]}
        errs = recap.validate(recap.normalize(r))
        self.assertTrue(any("phase 'B'" in e for e in errs))
        r["steps"][2]["phase"] = "A"
        self.assertEqual(recap.validate(recap.normalize(r)), [])
        d = {"agent": "codex", "session_id": "abc", "started_at": "2026-09-01T10:00:00+00:00", "languages": [{"lang": "go"}], "project": {"id": "github.com/me/app", "name": "app"}}
        n = recap.normalize(r, d)
        self.assertEqual(n["date"], "2026-09-01")
        self.assertEqual(n["languages"], ["go"])
        self.assertEqual(n["project"]["id"], "github.com/me/app")

    def test_redaction(self):
        text = "use sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789 and password: hunter2secret and ghp_" + "a" * 36
        out = store.redact_text(text)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", out)
        self.assertNotIn("hunter2secret", out)
        self.assertNotIn("a" * 36, out)
        self.assertIn("[redacted]", out)

    def test_effective_config(self):
        cfg = json.loads(json.dumps(config.DEFAULTS))
        config.set_value(cfg, "profile.coding", "new")
        config.set_value(cfg, "profile.prompting", "new")
        eff = config.effective(cfg)
        self.assertEqual((eff["voice"], eff["focus"]), ("plain", "prompts"))
        config.set_value(cfg, "profile.coding", "advanced")
        config.set_value(cfg, "profile.prompting", "advanced")
        eff = config.effective(cfg)
        self.assertEqual((eff["voice"], eff["focus"]), ("technical", "both"))
        with self.assertRaises(ValueError):
            config.set_value(cfg, "voice", "loud")

    def test_digest_from_session(self):
        from cartographer.adapters.base import Event, Session
        from datetime import datetime, timezone
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
        kinds = [x["kind"] for x in d["timeline"]]
        self.assertIn("pause", kinds)
        self.assertEqual(d["duration_min"], 30.0)


if __name__ == "__main__":
    unittest.main()
