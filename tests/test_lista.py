"""0.5.0: la lista se gestiona con ocultar y vaciar; el estado lo mueve la actividad, no los botones."""
import json
import os
import time
import unittest

import test_hooks


class Lista(unittest.TestCase):
    setUp, cli, hook, fiche = (test_hooks.Hooks.setUp, test_hooks.Hooks.cli,
                               test_hooks.Hooks.hook, test_hooks.Hooks.fiche)

    def own(self, aid="f", total="2"):
        self.cli("start", aid, "X", "--total", total, "--cwd", self.cwd)
        self.hook("PostToolUse", {"tool_name": "Bash", "tool_input": {"command": "progress step %s" % aid}})

    def test_step_unhides_and_reopens_paused_or_done(self):
        self.own()
        self.cli("hide", "f")
        self.assertTrue(self.fiche()["hidden"])
        self.cli("pause", "f")
        self.cli("step", "f", "uno")
        d = self.fiche()
        self.assertEqual((d.get("hidden"), d["status"]), (None, "active"))
        self.cli("step", "f", "dos"); self.cli("done", "f")
        self.cli("step", "f", "tres")
        self.assertEqual(self.fiche()["status"], "active")

    def test_plan_add_reopens_closed_plan(self):
        self.own()
        self.cli("plan", "f", "a=A"); self.cli("step", "f", "--key", "a"); self.cli("done", "f")
        self.cli("plan", "f", "--add", "b=B")
        self.assertEqual(self.fiche()["status"], "active")

    def test_prompt_and_agent_unhide(self):
        self.own()
        self.cli("hide", "f")
        self.hook("UserPromptSubmit", {"prompt": "sigue"})
        self.assertNotIn("hidden", self.fiche())
        self.cli("hide", "f")
        self.hook("PreToolUse", {"tool_name": "Agent", "tool_use_id": "toolu_1", "tool_input": {"description": "d"}})
        self.assertNotIn("hidden", self.fiche())

    def test_stop_closes_complete_plan_without_live_agents(self):
        self.own(total="1")
        self.hook("UserPromptSubmit", {"prompt": "x"})
        self.hook("PreToolUse", {"tool_name": "Agent", "tool_use_id": "toolu_2", "tool_input": {"run_in_background": False}})
        self.cli("step", "f", "uno")
        self.hook("Stop", {})
        self.assertEqual(self.fiche()["status"], "active")  # un agente sigue en marcha
        self.hook("PostToolUse", {"tool_name": "Agent", "tool_use_id": "toolu_2", "tool_input": {"run_in_background": False}})
        self.hook("Stop", {})
        self.assertEqual(self.fiche()["status"], "done")
        turns = json.load(open(os.path.join(self.dir, "_turns", "s1.json")))
        self.assertGreaterEqual(turns["turn_end"], turns["turn_start"])

    def test_stop_does_not_refresh_an_unfinished_plan(self):  # si no, nunca saldría «Parada»
        self.own(total="3")
        self.hook("UserPromptSubmit", {"prompt": "x"})
        before = self.fiche()["updated"]
        time.sleep(1.1)
        self.hook("Stop", {})
        self.assertEqual(self.fiche()["updated"], before)

    def test_done_keeps_live_agents_and_their_stop_still_lands(self):
        self.own()
        self.hook("PreToolUse", {"tool_name": "Agent", "tool_use_id": "toolu_3", "tool_input": {"subagent_type": "Explore"}})
        self.hook("SubagentStart", {"agent_id": "ag3", "agent_type": "Explore"})
        self.cli("done", "f")
        self.assertEqual(list(self.fiche()["children"].values())[0]["state"], "running")
        self.hook("SubagentStop", {"agent_id": "ag3"})
        self.assertEqual(list(self.fiche()["children"].values())[0]["state"], "delivered")

    def test_hidden_archived_after_7_days_and_restored_on_step(self):
        self.own()
        self.cli("hide", "f")
        p = os.path.join(self.dir, "f.json")
        d = json.load(open(p)); d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 8 * 86400))
        json.dump(d, open(p, "w"))
        self.cli("ls")
        self.assertFalse(os.path.exists(p))
        self.cli("step", "f", "vuelve")
        self.assertEqual((self.fiche()["done"], self.fiche().get("hidden")), (1, None))

    def test_closing_or_trimming_a_hidden_card_shows_it_again(self):
        for verb in ("done", "cancel"):
            aid = "h" + verb
            self.own(aid); self.cli("hide", aid); self.cli(verb, aid)
            self.assertNotIn("hidden", self.fiche(aid))
        self.own("hp"); self.cli("plan", "hp", "a=A", "b=B"); self.cli("hide", "hp")
        self.cli("plan", "hp", "--remove", "b")
        self.assertNotIn("hidden", self.fiche("hp"))

    def test_stop_closes_every_complete_plan_and_the_loose_one(self):
        self.own("p1", total="1"); self.own("p2", total="1")
        self.cli("step", "p1", "x"); self.cli("step", "p2", "x")
        self.cli("start", "suelta", "Sin dueño", "--total", "1", "--cwd", self.cwd)
        self.cli("step", "suelta", "x")  # sin hook: nadie la reclama
        self.hook("Stop", {"session_id": "otra"})  # un chat sin fichas propias en la carpeta
        self.assertEqual(self.fiche("suelta")["status"], "done")
        self.hook("Stop", {})
        self.assertEqual((self.fiche("p1")["status"], self.fiche("p2")["status"]), ("done", "done"))

    def test_card_remembers_the_last_chat_that_touched_it(self):
        self.cli("start", "f", "X", "--total", "2", "--cwd", self.cwd)
        cmd = {"tool_name": "Bash", "tool_input": {"command": "progress step f"}}
        term = {k: v for k, v in self.env.items() if k not in ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_HOST_SESSION_ID")}
        self.hook("PostToolUse", cmd, env=term)
        self.assertEqual((self.fiche()["chat"]["app"], self.fiche()["chat"]["id"]), ("cli", "s1"))
        env = dict(self.env, CLAUDE_CODE_ENTRYPOINT="claude-desktop",
                   CLAUDE_CODE_HOST_SESSION_ID="local_00000000-0000-4000-8000-000000000001")
        self.hook("PostToolUse", dict(cmd, session_id="s2"), env=env)
        self.assertEqual(self.fiche()["chat"]["id"], "local_00000000-0000-4000-8000-000000000001")

    def test_chat_target_without_desktop_lookup(self):
        import sys
        sys.path.insert(0, os.path.join(test_hooks.ROOT, "bin"))
        import progresslib as P
        local, cli = "local_00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"
        self.assertEqual(P.chat_target({"owner": cli}), ("cli", cli))
        self.assertEqual(P.chat_target({"chat": {"app": "desktop", "id": local}}), ("desktop", local))
        self.assertEqual(P.chat_target({"chat": {"app": "cli", "id": cli}}), ("cli", cli))
        self.assertIsNone(P.chat_target({"owner": "x; rm -rf /"}))

    def test_hide_refuses_closed(self):
        self.own(); self.cli("done", "f")
        with self.assertRaises(Exception):
            self.cli("hide", "f")


if __name__ == "__main__":
    unittest.main()
