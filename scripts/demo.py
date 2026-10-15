#!/usr/bin/env python3
"""Demo plan for screenshots and GIFs: a card that moves on its own, with no real data.

  scripts/demo.py                 run it: 5 steps, one every 4 s, a subagent on step 3
  scripts/demo.py --delay 2       faster
  scripts/demo.py --hold 3        stop after closing 3 steps (for still screenshots)
  scripts/demo.py --clean         remove the demo card (only that one; other cards are untouched)

The card has no owner and belongs to the folder given with --cwd (default: the current one), so the
band shows it in any session opened in that folder. Respects CLAUDE_PROGRESS_DIR.
"""
import argparse
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
AGENT = "a-demo0copywriter"


def cli(*args):
    subprocess.run([os.path.join(BIN, "progress"), *args], check=True, stdout=subprocess.DEVNULL)


def remove_demo():
    """Borra solo la ficha de la demo (la creó este script); el resto de fichas no se toca."""
    for d in (P.PROGRESS_DIR, os.path.join(P.PROGRESS_DIR, "_done")):
        try:
            os.remove(os.path.join(d, ID + ".json"))
        except FileNotFoundError:
            pass


def set_agent(state):
    with P.mutate(ID) as f:
        t = P.iso(P.now())
        c = f.setdefault("children", {}).setdefault(AGENT, {
            "label": "Review the copy", "type": "general-purpose", "background": True, "started": t,
        })
        c["state"], c["updated"] = state, t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--hold", type=int, default=len(STEPS))
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    remove_demo()
    if a.clean:
        return
    cli("start", ID, TITLE, "--total", str(len(STEPS)), "--cwd", a.cwd)
    cli("plan", ID, *("%s=%s" % (k, label) for k, label, _ in STEPS))
    for i, (key, _, closed) in enumerate(STEPS[: a.hold]):
        time.sleep(a.delay)
        if key == "copy":
            set_agent("running")
            time.sleep(a.delay)
            set_agent("delivered")
            time.sleep(a.delay / 2)
            set_agent("accepted")  # sin `child accept`, que sumaría un paso más al plan
        cli("step", ID, closed, "--key", key)
    if a.hold >= len(STEPS):
        time.sleep(a.delay)
        cli("done", ID)


if __name__ == "__main__":
    main()
