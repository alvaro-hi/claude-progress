"""Regresiones de la batería de estrés (robustez y volumen)."""
import json
import os
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "progress")
HOOK = os.path.join(ROOT, "bin", "progress_hook.py")


class R(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.dir = os.path.join(self.tmp, "p")
        self.env = dict(os.environ, CLAUDE_PROGRESS_DIR=self.dir)

    def cli(self, *a):
        return subprocess.run([CLI, *a], env=self.env, capture_output=True, text=True)

    def put(self, name, raw):
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, name + ".json"), "w", encoding="utf-8") as f:
            f.write(raw if isinstance(raw, str) else json.dumps(raw))

    def good(self, aid, **kw):
        d = {"id": aid, "title": aid, "cwd": self.tmp, "done": 1, "total": 4, "iter": None,
             "step": "", "status": "active", "started": "2026-01-01T00:00:00+00:00",
             "updated": "2026-01-01T00:00:00+00:00", "keys": [], "children": {}}
        d.update(kw)
        return d

    def test_mismatched_id_never_overwrites(self):  # 2f
        self.cli("start", "foo", "F", "--total", "3", "--cwd", self.tmp)
        self.cli("start", "otra", "Otra", "--total", "9", "--cwd", self.tmp)
        d = json.load(open(os.path.join(self.dir, "foo.json"))); d["id"] = "otra"
        self.put("foo", d)
        r = self.cli("step", "foo", "x")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(json.load(open(os.path.join(self.dir, "otra.json")))["title"], "Otra")

    def test_weird_fiches_no_traceback_and_bar_survives(self):  # 2a, 2b, 2g
        self.cli("start", "ok", "OK", "--total", "2", "--cwd", self.tmp)
        weird = {"s1": self.good("s1", total="4"), "s2": self.good("s2", children=[1]),
                 "s3": self.good("s3", iter=[1, 2, 3]), "s4": "", "s5": "[]", "s6": "\x00\x01",
                 "s7": self.good("s7", children={"c": "x"}),
                 "s8": {"id": 5, "status": "done", "updated": "2000-01-01T00:00:00+00:00"}}
        for k, v in weird.items():
            self.put(k, v)
        for args in (("ls",), ("step", "ok"), ("show", "s4"), ("step", "s3")):
            r = self.cli(*args)
            self.assertNotIn("Traceback", r.stderr, args)
        self.assertEqual(json.load(open(os.path.join(self.dir, "ok.json")))["done"], 1)

    def test_empty_cwd_matches_nothing(self):  # 2h
        self.put("e", self.good("e", cwd=""))
        r = subprocess.run([HOOK, "UserPromptSubmit"], input=json.dumps({"cwd": self.tmp, "session_id": "s"}),
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.stdout, "")

    def test_compound_emoji_kept(self):  # 5e
        self.cli("start", "em", "\U0001f468\u200d\U0001f4bb diseño \U0001f3f3\ufe0f\u200d\U0001f308", "--total", "1", "--cwd", self.tmp)
        self.assertIn("\U0001f468\u200d\U0001f4bb", json.load(open(os.path.join(self.dir, "em.json")))["title"])

    def test_config_not_dict_is_discreet(self):  # 2j
        self.put("_config", "[]")
        self.assertNotIn("Traceback", self.cli("discreet", "toggle").stderr)

    def test_turns_pruned_after_7_days(self):  # S8, decisión _turns
        td = os.path.join(self.dir, "_turns"); os.makedirs(td)
        old, new = os.path.join(td, "old.json"), os.path.join(td, "new.json")
        for p in (old, new):
            open(p, "w").write("{}")
        os.utime(old, (time.time() - 8 * 86400,) * 2)
        self.cli("ls")
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))


if __name__ == "__main__":
    unittest.main()
