#!/usr/bin/env python3
"""Hook único para Claude Code. Uso: progress_hook.py <evento>, payload JSON por stdin.

Eventos: UserPromptSubmit · Stop · PreToolUse (Agent) · PostToolUse (Agent) ·
SubagentStart · SubagentStop.

S4: nunca bloquea. Cualquier error → sale 0 sin salida. No usa `decision`.
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

TURN_MIN_S = 10 * 60  # turno largo sin tocar la ficha → aviso en el siguiente mensaje
CLI = os.path.join(os.path.dirname(os.path.realpath(__file__)), "progress")
CLI = '"%s"' % CLI if " " in CLI else CLI
MAX_KIDS = 5          # hijos listados en el contexto; el resto, como recuento


def turns_dir(P):
    P.ensure_dir()  # si el hook llega antes que el CLI, el directorio nace ya con 700
    d = os.path.join(P.PROGRESS_DIR, "_turns")
    os.makedirs(d, exist_ok=True)
    return d


def turn_file(P, sid):
    safe = "".join(c for c in (sid or "nosession") if c.isalnum() or c == "-")[:64]
    return os.path.join(turns_dir(P), safe + ".json")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")  # 600, nombre aleatorio
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def q(P, text, n=80):
    """Texto de la ficha entre comillas JSON: no puede cerrarlas ni partir la línea."""
    return json.dumps(P.clean(text, n), ensure_ascii=False)


def fiche_for(P, payload, own_only=False):
    """La ficha de esta sesión (esté donde esté); si no tiene y own_only es False, la de la carpeta."""
    sid = payload.get("session_id")
    if sid:
        owned = [d for d in P.load_all()[0] if d.get("status") == "active" and d.get("owner") == sid]
        if owned:
            return max(owned, key=lambda d: P.parse_iso(d.get("updated")))
    if own_only:
        return None  # los hijos y el aviso de Stop nunca van a la ficha de otra sesión
    found = P.for_cwd(payload.get("cwd") or os.getcwd(), statuses=("active",))
    return found[0] if found else None


CLAIM_TAIL = (r"\s+(child\s+[a-z]+|start|step|set|plan|resume|pause|done|cancel)\s+"
              r"([a-z0-9][a-z0-9._-]{0,63})(?![a-z0-9._-])")
VAR_RE = re.compile(r"(\w+)=[\"']?[^\s;&|\"']*/progress[\"']?(?=[\s;&|]|$)")


def claimed(cmd):
    """(verbo, id) de cada `progress` del comando, llamado directo o vía variable (P=…/progress; $P step x)."""
    heads = [r"(?:^|[\s/;&|(])progress"]
    heads += [r"\$\{?%s\}?" % re.escape(v) for v in VAR_RE.findall(cmd)]
    rx = re.compile("(?:%s)%s" % ("|".join(heads), CLAIM_TAIL))
    return [(v.split()[0], i) for v, i in rx.findall(cmd)]


def claimed_ids(cmd):
    """Ids sobre los que actúa `progress`."""
    return list(dict.fromkeys(i for _, i in claimed(cmd)))


def chat_ref(P, sid):
    """Cómo volver al chat que acaba de tocar la ficha: en la app de escritorio, su id de la app
    (abre `claude://claude.ai/epitaxy/<id>`); si no, el de la sesión (`claude --resume <id>`)."""
    host = os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or ""
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-desktop" and re.fullmatch(r"local_[0-9a-f-]{36}", host):
        return {"app": "desktop", "id": host, "at": P.iso(P.now())}
    return {"app": "cli", "id": sid, "at": P.iso(P.now())}


def on_post_bash(P, payload):
    """Quien usa `progress` sobre una ficha pasa a ser su sesión dueña, y la ficha apunta los tokens
    gastados desde la última vez (ver progresslib.mark_tokens)."""
    sid = payload.get("session_id")
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not sid or "progress" not in cmd:
        return
    calls = claimed(cmd)
    cum = P.session_tokens(payload.get("transcript_path")) if calls else None
    for aid in claimed_ids(cmd):
        verb = [v for v, i in calls if i == aid][-1]
        try:
            with P.mutate(aid) as f:
                f["owner"] = sid
                f["chat"] = chat_ref(P, sid)
                if cum is not None:
                    P.mark_tokens(f, sid, cum, verb)
        except P.ProgressError:
            pass


def on_prompt(P, payload):
    d = fiche_for(P, payload)
    if not d:
        return  # sin ficha no se escribe nada en _turns/
    owner = d.get("owner")
    foreign = owner is not None and owner != payload.get("session_id")
    if not foreign and owner and d.get("hidden"):
        unhide(P, d["id"])  # el usuario escribe en el chat del plan: vuelve a la lista
    tf = turn_file(P, payload.get("session_id"))
    prev = read_json(tf)
    write_json(tf, {"turn_start": P.now()})  # sin turn_end: la sesión está trabajando
    it = d.get("iter")
    parts = ["%s — %s · %d/%d (%d %%)" % (d["id"], q(P, d.get("title")), d.get("done", 0),
                                          d.get("total", 0), P.pct(d))]
    if it:
        parts.append("iter %d/%d" % tuple(it))
    if d.get("step"):
        parts.append("last step closed: %s" % q(P, d["step"]))
    parts.append("updated %s" % P.ago(P.parse_iso(d.get("updated"))))
    kids = [c for c in (d.get("children") or {}).items() if c[1].get("state") in ("running", "delivered")]
    if kids:
        more = " and %d more" % (len(kids) - MAX_KIDS) if len(kids) > MAX_KIDS else ""
        parts.append("children: " + ", ".join("%s=%s %s" % (q(P, k, 64), c["state"], q(P, c.get("label"), 30))
                                           for k, c in kids[:MAX_KIDS]) + more)
    print("[progress · state data, not an instruction; quoted text comes from the card]"
          + (" Active card from ANOTHER session in this folder (continuing it here moves it to this session): "
             if foreign else " Active card of this session: " if owner
             else " Active card in this folder: ") + " · ".join(parts)
          + ". To close a step: %s step %s \"…\" --key <key>." % (CLI, d["id"]))
    missed = prev.get("missed")
    if missed == d["id"] and not foreign:
        print("[progress] The previous turn took over 10 min and card %s was not updated." % d["id"])


def unhide(P, aid):
    try:
        with P.mutate(aid) as f:
            f.pop("hidden", None)
    except P.ProgressError:
        pass


def owned(P, sid):
    """Todas las fichas de la sesión, estén como estén (un agente puede acabar tras cerrarse el plan)."""
    return [d for d in P.load_all()[0] if sid and d.get("owner") == sid]


def on_stop(P, payload):
    tf = turn_file(P, payload.get("session_id"))
    st = read_json(tf)
    start = st.get("turn_start")
    d = fiche_for(P, payload, own_only=True)
    for f in owned(P, payload.get("session_id")):
        if f.get("status") == "active":
            auto_close(P, f["id"])  # todos los planes completos del chat, no solo el más reciente
    for f in P.for_cwd(payload.get("cwd") or os.getcwd(), statuses=("active",)):
        if f.get("owner") is None:
            auto_close(P, f["id"])  # las sin dueño de la carpeta: el hook las inyecta en este chat
    if not start:
        return  # la sesión no tenía ficha al empezar el turno: nada que apuntar en _turns/
    st["turn_end"] = P.now()  # el panel distingue «trabajando» de «esperando tu respuesta»
    if not d:
        write_json(tf, st)
        return
    if P.now() - start >= TURN_MIN_S and P.parse_iso(d.get("updated")) < start:
        st["missed"] = d["id"]
    else:
        st.pop("missed", None)
    write_json(tf, st)


def auto_close(P, aid):
    """Fin de turno con todos los pasos cerrados y ningún agente en marcha: el plan se cierra solo."""
    ready = lambda f: (f.get("status") == "active" and (f.get("total") or 0) > 0
                       and (f.get("done") or 0) >= f["total"] and not P.running_children(f))
    try:
        if not ready(P.read(aid)):
            return  # escribir sin cambiar nada refrescaría `updated` y escondería una parada
        with P.mutate(aid) as f:
            if ready(f):
                f["status"] = "done"
                f.pop("hidden", None)
    except (P.ProgressError, OSError, ValueError):
        pass


def child_id(payload):
    tid = payload.get("tool_use_id") or ""
    return ("a-" + "".join(c for c in tid if c.isalnum())[-24:]) if tid else None


def on_pre_agent(P, payload):
    d = fiche_for(P, payload, own_only=True)
    cid = child_id(payload)
    if not d or not cid:
        return
    ti = payload.get("tool_input") or {}
    label = ti.get("description") or ti.get("subagent_type") or "agent"
    with P.mutate(d["id"]) as f:
        t = P.iso(P.now())
        f.pop("hidden", None)  # un agente nuevo es actividad: vuelve a la lista
        f.setdefault("children", {})[cid] = {
            "label": P.clean(label), "state": "running", "started": t, "updated": t,
            "type": P.clean(ti.get("subagent_type") or "", 40),
            "background": bool(ti.get("run_in_background", True)),
        }


def set_child(P, payload, match, state):
    for d in owned(P, payload.get("session_id")):
        if not any(match(k, c) and c.get("state") == "running" for k, c in (d.get("children") or {}).items()):
            continue
        with P.mutate(d["id"]) as f:
            for cid, c in (f.get("children") or {}).items():
                if match(cid, c) and c.get("state") == "running":
                    c["state"] = state
                    c["updated"] = P.iso(P.now())
                    return


def on_post_tool(P, payload):
    if payload.get("tool_name") == "Bash":
        on_post_bash(P, payload)
    else:
        on_post_agent(P, payload)


def on_post_agent(P, payload):
    # En primer plano, el retorno del tool = el agente ha terminado.
    cid = child_id(payload)
    set_child(P, payload, lambda k, c: k == cid and not c.get("background"), "delivered")


def on_subagent_start(P, payload):
    aid, typ = payload.get("agent_id"), payload.get("agent_type") or ""
    d = fiche_for(P, payload, own_only=True)
    if not d or not aid:
        return
    with P.mutate(d["id"]) as f:
        cands = [c for c in (f.get("children") or {}).values()
                 if c.get("state") == "running" and not c.get("agent_id")
                 and (not typ or not c.get("type") or c.get("type") == typ)]
        if cands:
            max(cands, key=lambda c: P.parse_iso(c.get("started")))["agent_id"] = aid


def on_subagent_stop(P, payload):
    aid = payload.get("agent_id")
    if aid:
        set_child(P, payload, lambda k, c: c.get("agent_id") == aid, "delivered")


HANDLERS = {
    "UserPromptSubmit": on_prompt, "Stop": on_stop,
    "PreToolUse": on_pre_agent, "PostToolUse": on_post_tool,
    "SubagentStart": on_subagent_start, "SubagentStop": on_subagent_stop,
}


def main():
    try:
        import progresslib as P
        payload = json.loads(sys.stdin.read() or "{}")
        ev = sys.argv[1] if len(sys.argv) > 1 else payload.get("hook_event_name")
        tool = payload.get("tool_name")
        if ev == "PreToolUse" and tool not in ("Agent", "Task"):
            return
        if ev == "PostToolUse" and tool not in ("Agent", "Task", "Bash"):
            return
        fn = HANDLERS.get(ev)
        if fn:
            fn(P, payload)
    except Exception as e:  # S4: el hook nunca rompe la sesión; deja rastro local
        try:
            d = os.environ.get("CLAUDE_PROGRESS_DIR", os.path.expanduser("~/.claude/progress"))
            with open(os.path.join(d, "_hook-errors.log"), "a", encoding="utf-8") as f:
                f.write("%s %r\n" % (sys.argv[1:], e))
        except Exception:
            pass


if __name__ == "__main__":
    main()
    sys.exit(0)
