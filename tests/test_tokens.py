"""Tokens por paso y por plan: el hook los lee de la transcripción tras cada `progress`."""
import json
import os
import subprocess
import unittest

import test_hooks


def usage(mid, inp, out, cr=0, cw=0):
    return json.dumps({"type": "assistant", "message": {"id": mid, "usage": {
        "input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cr,
        "cache_creation_input_tokens": cw}}}) + "\n"


class Tokens(unittest.TestCase):
    setUp, cli, hook, fiche = (test_hooks.Hooks.setUp, test_hooks.Hooks.cli,
                                   test_hooks.Hooks.hook, test_hooks.Hooks.fiche)

    def say(self, *lines, agent=None):
        path = self.tr if not agent else os.path.join(self.tr[:-6], "subagents", agent + ".jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.writelines(lines)

    def run_(self, cmd, sid="s1"):
        args = cmd.split()[1:]
        self.cli(*(args + ["--cwd", self.cwd] if args[0] == "start" else args))
        self.hook("PostToolUse", {"session_id": sid, "tool_name": "Bash", "transcript_path": self.tr,
                                  "tool_input": {"command": cmd}})

    def test_step_and_plan_tokens(self):
        self.tr = os.path.join(self.tmp, "s1.jsonl")
        self.say(usage("m0", 1000, 1000))  # antes del plan: no cuenta
        self.run_("progress start f X --total 2")
        self.say(usage("m1", 10, 5), usage("m1", 10, 20))  # mismo id: cuenta la última línea
        self.say(usage("a1", 100, 0, cr=50), agent="agent-x")  # los agentes de la sesión también
        self.run_("progress step f uno --key a")
        self.say(usage("m2", 1, 2, cw=3))
        self.run_("progress step f dos --key b")
        d = self.fiche()
        self.assertEqual([r["tok"] for r in d["steps"]], [180, 6])
        self.assertEqual(d["tokens"], {"input": 111, "cache_write": 3, "cache_read": 50, "output": 22})

    def test_pause_and_other_session_do_not_count(self):
        self.tr = os.path.join(self.tmp, "s1.jsonl")
        self.say(usage("m0", 1, 1))
        self.run_("progress start f X --total 3")
        self.run_("progress pause f")
        self.say(usage("m1", 500, 500))  # en pausa
        self.run_("progress resume f")
        self.say(usage("m2", 4, 0))
        self.run_("progress step f uno --key a")
        self.assertEqual(self.fiche()["steps"][-1]["tok"], 4)
        self.tr = os.path.join(self.tmp, "s2.jsonl")  # otra sesión la toma sin resume
        self.say(usage("n1", 7, 0))
        self.run_("progress step f dos --key b", sid="s2")
        self.assertIsNone(self.fiche()["steps"][-1]["tok"])
        self.assertEqual(self.fiche()["tokens"]["input"], 4)

    def test_child_drop(self):
        self.cli("start", "f", "X", "--total", "2", "--cwd", self.cwd)
        self.cli("child", "add", "f", "c1", "agente")
        self.cli("child", "drop", "f", "c1")
        d = self.fiche()
        self.assertEqual((d["children"]["c1"]["state"], d["done"], d["total"]), ("rejected", 0, 2))


if __name__ == "__main__":
    unittest.main()
