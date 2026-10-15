#!/usr/bin/env python3
"""Clean stage for screenshots: hide every live card except the demo, then put them back.

  scripts/scene.py hide       hide every card but demo-landing (finished ones too) and remember which
  scripts/scene.py restore    unhide exactly those cards, and nothing else

Hiding is the CLI's own `hidden` mark: nothing is moved or deleted. Respects CLAUDE_PROGRESS_DIR.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin"))
import progresslib as P  # noqa: E402

DEMO = "demo-landing"
STATE = os.path.join(P.PROGRESS_DIR, "_scene.json")


def hide():
    """Se puede repetir justo antes de cada captura: suma a la lista, no la pisa."""
    try:
        with open(STATE, encoding="utf-8") as f:
            hidden = json.load(f)
    except FileNotFoundError:
        hidden = []
    for d in P.load_all()[0]:
        if d["id"] == DEMO or d.get("hidden"):
            continue
        with P.mutate(d["id"]) as f:
            f["hidden"] = True
        if d["id"] not in hidden:
            hidden.append(d["id"])
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(hidden, f)
    print("hidden: %s" % (", ".join(hidden) or "none"))


def restore():
    try:
        with open(STATE, encoding="utf-8") as f:
            ids = json.load(f)
    except FileNotFoundError:
        print("nothing to restore")
        return
    for aid in ids:
        try:
            with P.mutate(aid) as f:
                f.pop("hidden", None)
        except P.ProgressError:
            pass  # the card is gone (cleared or deleted meanwhile): nothing to put back
    os.remove(STATE)
    print("restored: %s" % (", ".join(ids) or "none"))


if __name__ == "__main__":
    {"hide": hide, "restore": restore}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
