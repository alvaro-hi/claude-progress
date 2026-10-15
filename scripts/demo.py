#!/usr/bin/env python3
"""Demo plan for screenshots and GIFs: a card that moves on its own, with no real data.

  scripts/demo.py                 run it: 5 steps, one every 4 s, subagents on steps 3 and 4
  scripts/demo.py --delay 2       faster
  scripts/demo.py --hold 3        stop after closing 3 steps, with step 4's subagent at work (for stills)
  scripts/demo.py --owner <sid>   the card belongs to that chat (the panel lists it under «In this chat»)
  scripts/demo.py --extras        also lay out more demo cards: other chats working, waiting, stalled
                                  and paused, and some finished or cancelled today
  scripts/demo.py --clean         remove every demo card (demo-*); other cards are untouched

Without --owner the card has no owner and belongs to the folder given with --cwd (default: the current
one), so the band shows it in any session opened in that folder. The extra cards of other chats have
made-up owners and folders. Respects CLAUDE_PROGRESS_DIR.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
sys.path.insert(0, BIN)
import progresslib as P  # noqa: E402

ID = "demo-landing"
TITLE = "Launch landing page"
STEPS = [
    ("brief", "Write the brief", "Brief approved"),
    ("wire", "Wireframes", "Wireframes for 3 sections"),
    ("copy", "Copy", "Copy reviewed by the subagent"),
    ("build", "Build the page", "Page built and tested"),
    ("ship", "Publish", "Live at /launch"),
]
AGENTS = {"copy": ("a-demo0copywriter", "Review the copy"), "build": ("a-demo0tester", "Run the test suite")}

FAKE = "00000000-0000-4000-8000-0000000000%s"  # dueños inventados: chats que no existen
# owner None = el chat de --owner. started/updated: minutos atrás. child: (etiqueta, estado, minutos).
EXTRAS = [
    dict(id="demo-audit", title="Audit the signup flow", owner=None, status="done", closed=4,
         plan=["Map the funnel", "Find the drop-offs", "Rank the fixes", "Write the report"],
         started=410, updated=350, tokens=182000),
    dict(id="demo-billing", title="Migrate billing to v2", owner="a1", status="active", closed=4,
         plan=["Inventory the endpoints", "Map the data model", "Dual-write layer", "Backfill invoices",
               "Port the webhooks", "Switch traffic", "Remove v1"],
         started=95, updated=2, working=True, child=("Test webhook retries", "running", 3)),
    dict(id="demo-onboarding", title="Onboarding email series", owner="a2", status="active", closed=2,
         plan=["Define the audience", "Outline the series", "Draft the emails", "Design the template",
               "Schedule the sends"],
         started=50, updated=6, child=("Draft email 3", "delivered", 9)),
    dict(id="demo-tests", title="Fix flaky checkout tests", owner="a3", status="active", closed=5,
         plan=["Reproduce locally", "Find the race", "Fix the fixture", "Guard the retries",
               "Run it 50 times", "Merge"],
         started=150, updated=42),
    dict(id="demo-docs", title="API reference docs", owner="a4", status="paused", closed=1,
         plan=["Pick the generator", "Annotate the endpoints", "Write the guides", "Add examples",
               "Review", "Publish"],
         started=260, updated=200),
    dict(id="demo-pricing", title="Pricing page experiment", owner="a5", status="done", closed=6,
         plan=["Pick the variants", "Build variant B", "Set up tracking", "Run the test",
               "Read the results", "Roll out the winner"],
         started=650, updated=500, tokens=420000),
    dict(id="demo-notes", title="Release notes for 2.3", owner="a6", status="done", closed=3,
         plan=["Collect the changes", "Draft the notes", "Publish"],
         started=290, updated=265, tokens=64000),
    dict(id="demo-mobile", title="Dark mode for the mobile app", owner="a7", status="cancelled", closed=2,
         plan=["Audit the colors", "Define the tokens", "Theme the screens", "Test contrast", "Ship"],
         started=480, updated=430),
]


def cli(*args):
    subprocess.run([os.path.join(BIN, "progress"), *args], check=True, stdout=subprocess.DEVNULL)


def remove(aid):
    """Borra una ficha de la demo (las crea este script); el resto de fichas no se toca."""
    for d in (P.PROGRESS_DIR, os.path.join(P.PROGRESS_DIR, "_done")):
        try:
            os.remove(os.path.join(d, aid + ".json"))
        except FileNotFoundError:
            pass


def turn_file(owner):
    return os.path.join(P.PROGRESS_DIR, "_turns", owner + ".json")


def clean_all():
    for d in (P.PROGRESS_DIR, os.path.join(P.PROGRESS_DIR, "_done")):
        for p in glob.glob(os.path.join(d, "demo-*.json")):
            os.remove(p)
    for p in glob.glob(turn_file(FAKE % "*")):
        os.remove(p)


def ago(minutes):
    """Hace N minutos, sin pasar de medianoche: las terminadas solo salen si son de hoy."""
    return max(P.now() - minutes * 60, P.midnight() + 60)


def backdate(aid, ts):
    """write() sella `updated` con la hora actual; las fichas de relleno llevan la suya."""
    with P.locked(aid):
        d = P.read(aid)
        d["updated"] = P.iso(ts)
        with open(P.path_for(aid), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)


def make_extra(e, owner, cwd):
    remove(e["id"])
    real_owner = owner if e["owner"] is None else FAKE % e["owner"]
    folder = cwd if e["owner"] is None else "/Users/demo/code/" + e["id"][len("demo-"):]
    P.new_activity(e["id"], e["title"], len(e["plan"]), cwd=folder)
    start, end = ago(e["started"]), ago(e["updated"])
    with P.mutate(e["id"]) as f:
        P.set_plan(f, ["s%d=%s" % (i + 1, label) for i, label in enumerate(e["plan"])])
        n = e["closed"]
        for i in range(n):
            P.close_step(f, e["plan"][i], key="s%d" % (i + 1))
            f["steps"][-1]["at"] = P.iso(start + (end - start) * (i + 1) / n)
        f["status"] = e["status"]
        f["started"] = P.iso(start)
        if real_owner:
            f["owner"] = real_owner
        if e.get("tokens"):
            tok = e["tokens"]
            f["tokens"] = {"input": tok // 10, "cache_write": tok // 5, "cache_read": tok // 2,
                           "output": tok - tok // 10 - tok // 5 - tok // 2}
        if e.get("child"):
            label, state, mins = e["child"]
            t = P.iso(ago(mins))
            f["children"] = {"a-demo0" + e["id"][5:]: {"label": label, "type": "general-purpose",
                                                        "background": True, "started": t,
                                                        "state": state, "updated": t}}
    backdate(e["id"], end)
    if e.get("working"):
        os.makedirs(os.path.dirname(turn_file(real_owner)), exist_ok=True)
        with open(turn_file(real_owner), "w", encoding="utf-8") as f:
            json.dump({"turn_start": P.now()}, f)


def set_agent(key, state):
    cid, label = AGENTS[key]
    with P.mutate(ID) as f:
        t = P.iso(P.now())
        c = f.setdefault("children", {}).setdefault(cid, {
            "label": label, "type": "general-purpose", "background": True, "started": t,
        })
        c["state"], c["updated"] = state, t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--hold", type=int, default=len(STEPS))
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--owner")
    ap.add_argument("--extras", action="store_true")
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    if a.clean:
        clean_all()
        return
    remove(ID)
    if a.extras:
        for e in EXTRAS:
            make_extra(e, a.owner, a.cwd)
    cli("start", ID, TITLE, "--total", str(len(STEPS)), "--cwd", a.cwd)
    if a.owner:
        with P.mutate(ID) as f:
            f["owner"] = a.owner
    cli("plan", ID, *("%s=%s" % (k, label) for k, label, _ in STEPS))
    for i, (key, _, closed) in enumerate(STEPS[: a.hold]):
        time.sleep(a.delay)
        if key in AGENTS:
            set_agent(key, "running")
            time.sleep(a.delay)
            set_agent(key, "delivered")
            time.sleep(a.delay / 2)
            set_agent(key, "accepted")  # sin `child accept`, que sumaría un paso más al plan
        cli("step", ID, closed, "--key", key)
    if a.hold < len(STEPS) and STEPS[a.hold][0] in AGENTS:
        time.sleep(a.delay)
        set_agent(STEPS[a.hold][0], "running")  # parada a medias: el paso en curso, con su agente trabajando
    if a.hold >= len(STEPS):
        time.sleep(a.delay)
        cli("done", ID)


if __name__ == "__main__":
    main()
