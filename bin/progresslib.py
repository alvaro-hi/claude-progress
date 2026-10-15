"""Registro de progreso compartido por el CLI y los hooks (el mod de Claude Code solo lo lee).

Una ficha = un JSON en PROGRESS_DIR/<id>.json. Escrituras con lock + rename
atómico para que varias sesiones puedan tocar la misma ficha a la vez.
Compatible con Python 3.9 (el python3 del sistema en macOS) y Linux.
"""
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone

PROGRESS_DIR = os.environ.get(
    "CLAUDE_PROGRESS_DIR", os.path.expanduser("~/.claude/progress")
)
DONE_DIR_NAME = "_done"
CONFIG_NAME = "_config.json"
ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")  # siempre con fullmatch: '$' deja pasar "abc\n"

STALE_ACTIVITY_S = 30 * 60   # actividad sin tocar y sin hijos vivos → «¿parada?»
STALE_NEAR_END_S = 15 * 60   # con uno o dos pasos por cerrar se avisa antes (igual que el mod)
PAUSED_STALE_S = 24 * 3600  # pausada sin tocar → «¿abandonada?»
STALE_CHILD_S = 60 * 60      # hijo en curso sin cerrar → «¿colgado?»
HIDDEN_KEEP_S = 7 * 86400    # ocultas sin actividad: a _done/ a los 7 días (se recuperan si vuelven a tocarse)
TURNS_KEEP_S = 7 * 86400     # _turns/: estado efímero, se poda
MAX_TEXT = 80

CHILD_STATES = ("running", "delivered", "accepted", "rejected")


class ProgressError(Exception):
    pass


def now():
    fake = os.environ.get("CLAUDE_PROGRESS_NOW")  # solo tests
    return float(fake) if fake else time.time()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_iso(s):
    """ISO → epoch. Acepta sufijo Z (3.9 no); una fecha futura cuenta como ahora."""
    try:
        if isinstance(s, str) and s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return min(datetime.fromisoformat(s).timestamp(), now())
    except (TypeError, ValueError, OverflowError, OSError):
        return 0.0


def clean(text, limit=MAX_TEXT):
    """Texto seguro para mostrar: sin saltos, sin control, sin '|', acotado."""
    if text is None:
        return ""
    s = str(text)
    # ZWJ y selector de variación se conservan: sin ellos los emoji compuestos se parten
    s = "".join(ch if ch.isprintable() or ch in "\u200d\ufe0f" else " " for ch in s)
    s = s.replace("|", "¦")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def ensure_dir():
    os.makedirs(os.path.join(PROGRESS_DIR, DONE_DIR_NAME), exist_ok=True)
    os.chmod(PROGRESS_DIR, 0o700)


def check_id(aid):
    if not (isinstance(aid, str) and ID_RE.fullmatch(aid)):
        raise ProgressError(
            "invalid id: %r (lowercase letters, digits, . _ -; max 64)" % aid
        )
    return aid


def path_for(aid):
    return os.path.join(PROGRESS_DIR, check_id(aid) + ".json")


@contextmanager
def locked(aid):
    ensure_dir()
    lock_path = os.path.join(PROGRESS_DIR, "." + check_id(aid) + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read(aid):
    """Lee y valida: una ficha cuyo id no es su nombre de archivo no se toca (evita sobrescribir otra)."""
    try:
        with open(path_for(aid), encoding="utf-8-sig") as f:
            d = json.load(f)
    except ValueError:
        raise ProgressError("card %r is not valid JSON; fix or delete it by hand" % aid)
    if not valid_fiche(d, aid):
        raise ProgressError("card %r has an invalid format (id, numbers or children)" % aid)
    return d


def write(data):
    ensure_dir()
    data["updated"] = iso(now())
    fd, tmp = tempfile.mkstemp(dir=PROGRESS_DIR, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path_for(data["id"]))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextmanager
def mutate(aid):
    """Lectura-modificación-escritura bajo lock."""
    with locked(aid):
        if not os.path.exists(path_for(aid)) and not restore(aid):
            raise ProgressError("no card %r" % aid)
        data = read(aid)
        yield data
        write(data)


def new_activity(aid, title, total, iters=None, cwd=None):
    with locked(aid):
        if os.path.exists(path_for(aid)):
            raise ProgressError("card %r already exists (use set or done)" % aid)
        t = iso(now())
        data = {
            "id": aid,
            "title": clean(title),
            "cwd": os.path.realpath(cwd or os.getcwd()),
            "done": 0,
            "total": max(0, int(total)),
            "iter": [1, int(iters)] if iters else None,
            "step": "",
            "status": "active",
            "started": t,
            "updated": t,
            "keys": [],
            "children": {},
        }
        write(data)
        return data


def pct(data):
    total = data.get("total") or 0
    done = data.get("done") or 0
    if total <= 0:
        return 100 if data.get("status") == "done" else 0
    return max(0, min(100, int(round(100.0 * done / total))))


def close_step(data, label=None, key=None):
    """Suma un paso y lo apunta en el historial. Con key, idempotente: la misma clave no cuenta dos veces."""
    if key:
        key = clean(key, 64)
        if key in data.setdefault("keys", []):
            return False
        data["keys"].append(key)
    data["done"] = int(data.get("done") or 0) + 1
    touch(data)
    if label:
        data["step"] = clean(label)
    data.setdefault("steps", []).append(
        {"key": key or "", "label": clean(label) if label else "", "at": iso(now())})
    recompute_total(data)
    return True


def touch(data):
    """Actividad sobre la ficha: vuelve a la lista si estaba oculta y a «en curso» si estaba
    pausada, cerrada sola o cancelada. Es lo que dice la ficha: el plan se está moviendo."""
    data.pop("hidden", None)
    if data.get("status") != "active":
        data["status"] = "active"


def reopen_if_short(data):
    """Tras replanificar: una ficha cerrada con pasos por hacer vuelve a «en curso»."""
    data.pop("hidden", None)
    if data.get("status") == "done" and (data.get("done") or 0) < (data.get("total") or 0):
        data["status"] = "active"


def _plan_items(items, taken=()):
    """'clave=Etiqueta' → [{key, label}]; sin claves repetidas, ni entre sí ni con las que ya hay."""
    out, seen = [], set(taken)
    for item in items:
        key, sep, label = item.partition("=")
        key = clean(key, 64)
        if not sep or not key or not clean(label):
            raise ProgressError("invalid plan step: %r (write it as key=\"Label\")" % item)
        if key in seen:
            raise ProgressError("duplicate key in plan: %r" % key)
        seen.add(key)
        out.append({"key": key, "label": clean(label)})
    return out


def recompute_total(data):
    """Con plan, el total son sus pasos más los cerrados fuera de él; añadir o quitar pasos lo mueve.
    Sin plan no se toca: lo fija start o set."""
    plan = data.get("plan")
    if not plan:
        return
    planned = {p.get("key") for p in plan}
    closed_in_plan = sum(1 for k in data.get("keys") or [] if k in planned)
    extras = max(0, int(data.get("done") or 0) - closed_in_plan)
    data["total"] = len(plan) + extras


def set_plan(data, items):
    """Sustituye el plan entero."""
    data["plan"] = _plan_items(items)
    recompute_total(data)
    reopen_if_short(data)


def add_to_plan(data, items, after=None):
    """Añade pasos al final o detrás de la clave `after`."""
    plan = list(data.get("plan") or [])
    new = _plan_items(items, taken=[p["key"] for p in plan])
    if after:
        after = clean(after, 64)
        idx = next((i for i, p in enumerate(plan) if p["key"] == after), None)
        if idx is None:
            raise ProgressError("no step %r in the plan" % after)
        plan[idx + 1:idx + 1] = new
    else:
        plan.extend(new)
    data["plan"] = plan
    recompute_total(data)
    reopen_if_short(data)


def remove_from_plan(data, keys):
    """Quita pasos pendientes del plan; uno ya cerrado no se quita (su trabajo está hecho)."""
    plan = list(data.get("plan") or [])
    for key in keys:
        key = clean(key, 64)
        if key in (data.get("keys") or []):
            raise ProgressError("step %r is already closed; it cannot be removed from the plan" % key)
        if not any(p["key"] == key for p in plan):
            raise ProgressError("no step %r in the plan" % key)
        plan = [p for p in plan if p["key"] != key]
    data["plan"] = plan
    data.pop("hidden", None)
    recompute_total(data)


def config():
    try:
        with open(os.path.join(PROGRESS_DIR, CONFIG_NAME), encoding="utf-8-sig") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {"discreet": True}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {"discreet": True}  # config rota: fallar hacia el lado discreto


def set_config(**kw):
    ensure_dir()
    cfg = config()
    cfg.update(kw)
    p = os.path.join(PROGRESS_DIR, CONFIG_NAME)
    fd, tmp = tempfile.mkstemp(dir=PROGRESS_DIR, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    os.replace(tmp, p)
    return cfg


def load_all():
    """Devuelve (fichas válidas, nombres de fichas ilegibles). Nunca lanza."""
    good, bad = [], []
    try:
        names = sorted(os.listdir(PROGRESS_DIR))
    except FileNotFoundError:
        return good, bad
    except OSError:
        return good, ["(progress directory unreadable)"]
    for name in names:
        if not name.endswith(".json") or name.startswith((".", "_")):
            continue
        p = os.path.join(PROGRESS_DIR, name)
        try:
            with open(p, encoding="utf-8-sig") as f:
                d = json.load(f)
            if not valid_fiche(d, name[:-5]):
                raise ValueError("invalid card")
            good.append(d)
        except FileNotFoundError:
            continue  # borrada entre listdir y open: no es una ficha rota
        except (OSError, ValueError, RecursionError):
            bad.append(name[:-5])
    return good, bad


def valid_fiche(d, stem):
    """id = nombre del archivo; lo que se pinta o se inyecta, del tipo que escribe el CLI."""
    if not isinstance(d, dict) or d.get("id") != stem or not ID_RE.fullmatch(stem):
        return False
    it, kids = d.get("iter"), d.get("children") or {}
    rows = [d.get("steps", []), d.get("plan", [])]
    return (all(type(d.get(k, 0)) is int for k in ("done", "total"))
            and all(isinstance(r, list) and all(isinstance(x, dict) for x in r) for r in rows)
            and (it is None or (isinstance(it, list) and len(it) == 2
                                and all(type(x) is int for x in it)))
            and isinstance(d.get("cwd", ""), str)
            and isinstance(kids, dict) and all(isinstance(c, dict) for c in kids.values()))


def midnight(t=None):
    """Las 00:00 de hoy, hora local: «terminadas hoy» es hoy de verdad, no las últimas 24 h."""
    lt = time.localtime(t or now())
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _archive(d):
    src = path_for(d["id"])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(PROGRESS_DIR, DONE_DIR_NAME, "%s-%s.json" % (d["id"], stamp))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        shutil.move(src, dst)
        return True
    except OSError:
        return False


def clear():
    """Vaciar: las cerradas (terminadas y canceladas) a _done/ ya. No borra nada."""
    return [d["id"] for d in load_all()[0] if d.get("status") in ("done", "cancelled") and _archive(d)]


def restore(aid):
    """Una ficha oculta que se archivó por inactividad vuelve si alguien la toca."""
    ddir = os.path.join(PROGRESS_DIR, DONE_DIR_NAME)
    names = sorted(n for n in (os.listdir(ddir) if os.path.isdir(ddir) else ())
                   if re.fullmatch(re.escape(aid) + r"-\d{8}-\d{6}\.json", n))
    if not names:
        return False
    src = os.path.join(ddir, names[-1])
    try:
        with open(src, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    if not (isinstance(d, dict) and d.get("hidden") and d.get("status") in ("active", "paused")):
        return False  # solo vuelven las archivadas por ocultas; las cerradas siguen cerradas
    shutil.move(src, path_for(aid))
    return True


def gc():
    """Mueve a _done/ las cerradas antes de hoy y las ocultas 7 días sin actividad. No borra nada."""
    moved = []
    for d in load_all()[0]:
        st, upd = d.get("status"), parse_iso(d.get("updated"))
        closed_before_today = st in ("done", "cancelled") and upd < midnight()
        hidden_long = d.get("hidden") and st in ("active", "paused") and now() - upd > HIDDEN_KEEP_S
        if (closed_before_today or hidden_long) and _archive(d):
            moved.append(d["id"])
    # _turns/ es estado efímero de sesión (inicio del turno): se poda a los 7 días
    tdir = os.path.join(PROGRESS_DIR, "_turns")
    for n in (os.listdir(tdir) if os.path.isdir(tdir) else ()):
        p = os.path.join(tdir, n)
        try:
            if now() - os.path.getmtime(p) > TURNS_KEEP_S:
                os.remove(p)
        except OSError:
            pass
    return moved


def running_children(data):
    return [c for c in (data.get("children") or {}).values() if c.get("state") == "running"]


def is_stale(data, t=None):
    t = t or now()
    if data.get("status") != "active":
        return False
    if running_children(data):
        return False
    left = (data.get("total") or 0) - (data.get("done") or 0)
    limit = STALE_NEAR_END_S if 0 < left <= 2 else STALE_ACTIVITY_S
    return t - parse_iso(data.get("updated")) > limit


def child_hung(child, t=None):
    t = t or now()
    return child.get("state") == "running" and t - parse_iso(child.get("started")) > STALE_CHILD_S


def ago(ts, t=None):
    s = max(0, int((t or now()) - ts))
    if s < 60:
        return "%d s ago" % s
    if s < 3600:
        return "%d min ago" % (s // 60)
    if s < 86400:
        return "%d h ago" % (s // 3600)
    return "%d d ago" % (s // 86400)


def for_cwd(cwd, statuses=("active", "paused")):
    """Fichas cuyo cwd es cwd o un ancestro suyo: la más específica primero; a igualdad, la más reciente."""
    rc = unicodedata.normalize("NFC", os.path.realpath(cwd))
    out = []
    for d in load_all()[0]:
        if d.get("status") not in statuses:
            continue
        c = unicodedata.normalize("NFC", d.get("cwd") or "").rstrip("/")
        if not c:
            continue  # cwd vacío casaría con todas las carpetas
        if rc == c or rc.startswith(c + "/"):
            out.append(d)
    out.sort(key=lambda d: (len(d.get("cwd") or ""), parse_iso(d.get("updated"))), reverse=True)
    return out


# ── Tokens ────────────────────────────────────────────────────────────────────────────────────
# Lo que la sesión ha gastado se lee de su transcripción (y de las de sus agentes): cada respuesta
# del modelo deja su `usage`. La ficha guarda el acumulado del plan y, en cada paso, el acumulado al
# cerrarlo; el gasto de un paso es la diferencia con el anterior.

TOKEN_KINDS = ("input", "cache_write", "cache_read", "output")
_USAGE_KEYS = {"input": "input_tokens", "cache_write": "cache_creation_input_tokens",
               "cache_read": "cache_read_input_tokens", "output": "output_tokens"}


def _file_usage(path, by_id):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                m = o.get("message") if isinstance(o, dict) else None
                u = m.get("usage") if isinstance(m, dict) else None
                if o.get("type") != "assistant" or not isinstance(u, dict):
                    continue
                # una respuesta se escribe en varias líneas con el mismo id: cuenta la última
                by_id[(path, m.get("id") or len(by_id))] = u
    except OSError:
        pass


def session_tokens(transcript):
    """Acumulado de la sesión (con sus agentes) por tipo; None si no hay transcripción."""
    if not transcript or not os.path.isfile(transcript):
        return None
    by_id = {}
    _file_usage(transcript, by_id)
    sub = os.path.join(transcript[:-6] if transcript.endswith(".jsonl") else transcript, "subagents")
    for n in (sorted(os.listdir(sub)) if os.path.isdir(sub) else ()):
        if n.endswith(".jsonl"):
            _file_usage(os.path.join(sub, n), by_id)
    out = dict.fromkeys(TOKEN_KINDS, 0)
    for u in by_id.values():
        for k, src in _USAGE_KEYS.items():
            v = u.get(src)
            out[k] += v if type(v) is int and v > 0 else 0
    return out


def tokens_total(t):
    return sum(t.get(k, 0) for k in TOKEN_KINDS) if isinstance(t, dict) else 0


def mark_tokens(data, sid, cum, verb):
    """Tras un `progress <verb>` de la sesión sid: suma al plan, y al paso en curso, lo gastado desde
    la última marca, si la marca es de esta sesión. start y resume solo marcan: lo de antes no es de
    este plan. Los pasos recién cerrados se llevan lo del paso; sin marca previa, se quedan sin cifra."""
    mark = data.get("tokmark") or {}
    known = mark.get("sid") == sid and isinstance(mark.get("cum"), dict) and verb not in ("start", "resume")
    plan = data.setdefault("tokens", dict.fromkeys(TOKEN_KINDS, 0))
    if known:
        for k in TOKEN_KINDS:
            d = max(0, cum.get(k, 0) - mark["cum"].get(k, 0))
            plan[k] = plan.get(k, 0) + d
            data["tokstep"] = data.get("tokstep", 0) + d
    fresh = [r for r in data.get("steps") or [] if isinstance(r, dict) and "tok" not in r]
    for i, r in enumerate(fresh):
        r["tok"] = (data.get("tokstep", 0) if i == 0 else 0) if known else None
    if fresh:
        data["tokstep"] = 0
    data["tokmark"] = {"sid": sid, "cum": {k: cum.get(k, 0) for k in TOKEN_KINDS}}


# ── Volver al chat ────────────────────────────────────────────────────────────────────────────
# La app de escritorio guarda cada chat en claude-code-sessions/<cuenta>/<org>/local_<id>.json con el
# id de su sesión del motor (`cliSessionId`). Con eso, una ficha que solo sabe su dueña (fichas viejas)
# también puede abrir su chat en la app.

# Solo existe en macOS; en Linux la carpeta no está y chat_target cae a `claude --resume <id>`.
APP_SESSIONS = os.path.expanduser(
    "~/Library/Application Support/Claude/claude-code-sessions" if sys.platform == "darwin"
    else "~/.config/Claude/claude-code-sessions")
DESKTOP_ID_RE = re.compile(r"local_[0-9a-f-]{36}")
CLI_ID_RE = re.compile(r"[0-9a-f-]{36}")


def desktop_chat_for(cli_id, root=None):
    """El id de la app (`local_…`) del chat de escritorio cuya sesión del motor es cli_id; None si no hay."""
    root = root or os.environ.get("CLAUDE_APP_SESSIONS_DIR") or APP_SESSIONS
    if not CLI_ID_RE.fullmatch(cli_id or ""):
        return None
    for dirpath, _, names in os.walk(root):
        for n in names:
            if not (n.startswith("local_") and n.endswith(".json")):
                continue
            try:
                with open(os.path.join(dirpath, n), encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and d.get("cliSessionId") == cli_id and DESKTOP_ID_RE.fullmatch(str(d.get("sessionId"))):
                return d["sessionId"]
    return None


def desktop_chat_title(local_id, root=None):
    """El título que la app da al chat `local_…` (lo nombra el usuario o la app); None si no lo tiene."""
    root = root or os.environ.get("CLAUDE_APP_SESSIONS_DIR") or APP_SESSIONS
    if not DESKTOP_ID_RE.fullmatch(local_id or ""):
        return None
    name = local_id + ".json"
    for dirpath, _, names in os.walk(root):
        if name not in names:
            continue
        try:
            with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        return (clean(d.get("title")) or None) if isinstance(d, dict) else None
    return None


def chat_target(data):
    """Cómo volver al último chat de la ficha: ("desktop", local_id) o ("cli", session_id); None si no se sabe."""
    c = data.get("chat") if isinstance(data.get("chat"), dict) else {}
    if c.get("app") == "desktop" and DESKTOP_ID_RE.fullmatch(str(c.get("id"))):
        return "desktop", c["id"]
    sid = c.get("id") if c.get("app") == "cli" else data.get("owner")
    if not CLI_ID_RE.fullmatch(str(sid or "")):
        return None
    local = desktop_chat_for(sid)
    return ("desktop", local) if local else ("cli", sid)
