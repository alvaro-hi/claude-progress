"""Tests del CLI y la librería. Ejecutar: python3 -m unittest discover tests"""
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "progress")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self.tmp, "progress")
        self.env = dict(os.environ, CLAUDE_PROGRESS_DIR=self.dir)

    def run_cli(self, *args, ok=True):
        r = subprocess.run([CLI, *args], env=self.env, capture_output=True, text=True, timeout=20)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def fiche(self, aid):
        with open(os.path.join(self.dir, aid + ".json"), encoding="utf-8") as f:
            return json.load(f)


class TestF1Percent(Base):
    def test_basic(self):
        self.run_cli("start", "a", "A", "--total", "4", "--cwd", self.tmp)
        self.assertIn("1/4 · 25%", self.run_cli("step", "a").stdout)
        self.assertIn("2/4 · 50%", self.run_cli("step", "a", "x").stdout)
        self.assertEqual(self.fiche("a")["step"], "x")

    def test_total_zero_and_overflow(self):
        self.run_cli("start", "z", "Z", "--total", "0", "--cwd", self.tmp)
        self.assertIn("0%", self.run_cli("step", "z").stdout)
        self.run_cli("start", "o", "O", "--total", "1", "--cwd", self.tmp)
        self.run_cli("step", "o"); out = self.run_cli("step", "o").stdout
        self.assertIn("2/1 · 100%", out)

    def test_replan(self):
        self.run_cli("start", "r", "R", "--total", "4", "--cwd", self.tmp)
        self.run_cli("step", "r"); self.run_cli("step", "r")
        self.assertIn("2/8 · 25%", self.run_cli("set", "r", "--total", "8").stdout)


class TestF3Concurrency(Base):
    def test_parallel_writers(self):
        self.run_cli("start", "c", "C", "--total", "200", "--cwd", self.tmp)
        script = "for i in $(seq 100); do %s step c >/dev/null || echo FAIL; done" % CLI
        procs = [subprocess.Popen(["/bin/bash", "-c", script], env=self.env,
                                  stdout=subprocess.PIPE, text=True) for _ in range(2)]
        outs = [p.communicate(timeout=180)[0] for p in procs]
        self.assertNotIn("FAIL", "".join(outs))
        self.assertEqual(self.fiche("c")["done"], 200)
        leftovers = [n for n in os.listdir(self.dir) if n.startswith(".tmp-")]
        self.assertEqual(leftovers, [])


class TestF4Broken(Base):
    def test_broken_file_listed_not_fatal(self):
        self.run_cli("start", "ok", "OK", "--total", "2", "--cwd", self.tmp)
        with open(os.path.join(self.dir, "rota.json"), "w") as f:
            f.write('{"id": "rota", "done": ')
        out = self.run_cli("ls").stdout
        self.assertIn("ok ·", out)
        self.assertIn("unreadable rota", out)


class TestF9Keys(Base):
    def test_idempotent_key(self):
        self.run_cli("start", "k", "K", "--total", "3", "--cwd", self.tmp)
        self.run_cli("step", "k", "--key", "anexo-c")
        out = self.run_cli("step", "k", "--key", "anexo-c").stdout
        self.assertIn("no change", out)
        self.assertEqual(self.fiche("k")["done"], 1)

    def test_child_accept_counts_once(self):
        self.run_cli("start", "h", "H", "--total", "3", "--cwd", self.tmp)
        self.run_cli("child", "add", "h", "a1", "Anexo C")
        self.run_cli("child", "deliver", "h", "a1")
        self.assertEqual(self.fiche("h")["done"], 0)  # entregado ≠ aceptado
        self.run_cli("child", "reject", "h", "a1")
        self.assertEqual(self.fiche("h")["children"]["a1"]["state"], "running")
        self.run_cli("child", "deliver", "h", "a1")
        self.run_cli("child", "accept", "h", "a1")
        self.run_cli("child", "accept", "h", "a1")
        self.assertEqual(self.fiche("h")["done"], 1)


class TestCancel(Base):
    def test_cancelled_stays_today_and_clear_moves_it(self):
        self.run_cli("start", "x", "X", "--total", "3", "--cwd", self.tmp)
        self.assertIn("cancelled", self.run_cli("cancel", "x").stdout)
        self.run_cli("ls")  # gc: se ve hasta medianoche, como las terminadas
        self.assertTrue(os.path.exists(os.path.join(self.dir, "x.json")))
        self.assertIn("cleared 1", self.run_cli("clear").stdout)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "x.json")))
        self.assertEqual(len(os.listdir(os.path.join(self.dir, "_done"))), 1)


class TestS6Safety(Base):
    def test_permissions_and_ids(self):
        self.run_cli("start", "p", "P", "--total", "1", "--cwd", self.tmp)
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.dir, "p.json")).st_mode), 0o600)
        for bad in ("../x", "A B", "", "x/y", "-rf", "x\n"):
            r = self.run_cli("start", bad, "t", "--total", "1", ok=False)
            self.assertNotEqual(r.returncode, 0, bad)

    def test_text_sanitized(self):
        self.run_cli("start", "t", "a|b\nc\x07" + "x" * 200, "--total", "1", "--cwd", self.tmp)
        title = self.fiche("t")["title"]
        self.assertNotIn("|", title); self.assertNotIn("\n", title)
        self.assertLessEqual(len(title), 80)


class TestS8GC(Base):
    def test_done_moved_not_deleted(self):
        self.run_cli("start", "g", "G", "--total", "1", "--cwd", self.tmp)
        self.run_cli("done", "g")
        p = os.path.join(self.dir, "g.json")
        d = self.fiche("g"); d["updated"] = "2000-01-01T00:00:00+00:00"
        with open(p, "w") as f:
            json.dump(d, f)
        self.run_cli("ls")
        self.assertFalse(os.path.exists(p))
        self.assertEqual(len(os.listdir(os.path.join(self.dir, "_done"))), 1)

    def test_foreign_id_does_not_move_nor_block(self):  # S8: el id manda el nombre, no el contenido
        self.run_cli("start", "ok", "OK", "--total", "2", "--cwd", self.tmp)
        for name, aid in (("zzz", "ok"), ("mala", "Mala Id")):
            with open(os.path.join(self.dir, name + ".json"), "w") as f:
                json.dump({"id": aid, "status": "done", "updated": "2000-01-01T00:00:00+00:00"}, f)
        self.run_cli("step", "ok")
        self.assertEqual(self.fiche("ok")["done"], 1)


class TestSteps(Base):
    def test_history_records_each_close_once(self):
        self.run_cli("start", "s", "S", "--total", "3", "--cwd", self.tmp)
        self.run_cli("step", "s", "Primero", "--key", "uno")
        self.run_cli("step", "s", "Otra vez", "--key", "uno")  # clave ya cerrada: ni suma ni se apunta
        self.run_cli("step", "s")
        steps = self.fiche("s")["steps"]
        self.assertEqual([(x["key"], x["label"]) for x in steps], [("uno", "Primero"), ("", "")])
        self.assertTrue(all(x["at"] for x in steps))

    def test_child_accept_goes_to_history(self):
        self.run_cli("start", "h", "H", "--total", "2", "--cwd", self.tmp)
        self.run_cli("child", "add", "h", "a1", "Anexo C")
        self.run_cli("child", "accept", "h", "a1")
        self.assertEqual(self.fiche("h")["steps"][0]["key"], "child:a1")
        self.assertEqual(self.fiche("h")["steps"][0]["label"], "Anexo C")

    def test_plan_sets_pending_and_total(self):
        self.run_cli("start", "p", "P", "--total", "1", "--cwd", self.tmp)
        out = self.run_cli("plan", "p", "api=Leer la API", "mod=Escribir el mod", "tests=Tests").stdout
        self.assertIn("0/3 · 0%", out)
        self.assertEqual([x["key"] for x in self.fiche("p")["plan"]], ["api", "mod", "tests"])
        self.run_cli("plan", "p", "api=Leer la API")  # sustituir el plan también mueve el total
        self.assertEqual(len(self.fiche("p")["plan"]), 1)
        self.assertEqual(self.fiche("p")["total"], 1)

    def test_add_and_remove_move_the_total(self):
        self.run_cli("start", "m", "M", "--total", "1", "--cwd", self.tmp)
        self.run_cli("plan", "m", "a=A", "b=B", "c=C")
        self.run_cli("step", "m", "--key", "a")
        self.assertIn("1/4", self.run_cli("plan", "m", "--add", "x=Extra", "--after", "a").stdout)
        self.assertEqual([p["key"] for p in self.fiche("m")["plan"]], ["a", "x", "b", "c"])
        self.assertIn("1/3", self.run_cli("plan", "m", "--remove", "x").stdout)
        self.assertNotEqual(self.run_cli("plan", "m", "--remove", "a", ok=False).returncode, 0)  # cerrado: no se quita
        self.assertNotEqual(self.run_cli("plan", "m", "--add", "b=Otra", ok=False).returncode, 0)  # clave repetida
        self.assertNotEqual(self.run_cli("plan", "m", "--add", "y=Y", "--after", "nada", ok=False).returncode, 0)
        self.assertEqual(self.fiche("m")["total"], 3)

    def test_set_total_refused_when_there_is_a_plan(self):
        self.run_cli("start", "s", "S", "--total", "2", "--cwd", self.tmp)
        self.run_cli("plan", "s", "a=A", "b=B")
        r = self.run_cli("set", "s", "--total", "5", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("plan --add", r.stderr)
        self.assertEqual(self.fiche("s")["total"], 2)
        self.run_cli("start", "n", "N", "--total", "2", "--cwd", self.tmp)  # sin plan, set --total sigue valiendo
        self.assertIn("0/5", self.run_cli("set", "n", "--total", "5").stdout)

    def test_step_outside_the_plan_grows_the_total(self):
        self.run_cli("start", "o", "O", "--total", "1", "--cwd", self.tmp)
        self.run_cli("plan", "o", "a=A", "b=B")
        self.assertIn("1/3", self.run_cli("step", "o", "imprevisto").stdout)

    def test_plan_rejects_bad_items(self):
        self.run_cli("start", "b", "B", "--total", "1", "--cwd", self.tmp)
        for bad in (["sin-igual"], ["=Sin clave"], ["k="], ["k=A", "k=B"]):
            self.assertNotEqual(self.run_cli("plan", "b", *bad, ok=False).returncode, 0, bad)
        self.assertNotIn("plan", self.fiche("b"))

    def test_bad_steps_shape_is_unreadable(self):
        self.run_cli("start", "ok", "OK", "--total", "1", "--cwd", self.tmp)
        with open(os.path.join(self.dir, "mal.json"), "w") as f:
            json.dump({"id": "mal", "done": 0, "total": 1, "steps": "no es lista"}, f)
        self.assertIn("unreadable mal", self.run_cli("ls").stdout)


class TestStaleNearEnd(unittest.TestCase):
    def test_near_end_warns_sooner(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "bin"))
        import progresslib as P
        t = 1_000_000_000
        base = {"status": "active", "children": {}, "updated": P.iso(t - 20 * 60)}
        self.assertTrue(P.is_stale(dict(base, done=8, total=9), t))   # falta 1: avisa a los 15 min
        self.assertFalse(P.is_stale(dict(base, done=2, total=9), t))  # faltan 7: espera a los 30
        self.assertFalse(P.is_stale(dict(base, done=9, total=9), t))  # todo cerrado: el umbral normal


if __name__ == "__main__":
    unittest.main()
