// Lógica pura, espejo de ~/code/claude-progress/bin/progresslib.py: sin $, sin efectos.
import type { Child, Ficha, Snap, StepRow } from '../types'
import type { Dict } from './i18n'

export const ID_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/
export const STALE_ACTIVITY_MS = 30 * 60_000 // actividad sin tocar y sin hijos vivos → «¿parada?»
export const STALE_NEAR_END_MS = 15 * 60_000 // con uno o dos pasos por cerrar, una pausa pesa más: se avisa antes
export const PAUSED_STALE_MS = 24 * 3_600_000 // pausada sin tocar → «¿abandonada?»
export const STALE_CHILD_MS = 60 * 60_000 // hijo en curso sin cerrar → «¿colgado?»

const GLYPHS = '○◔◑◕●'

type Json = Record<string, unknown>

const isObj = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v)
const str = (v: unknown): string => (typeof v === 'string' ? v : '')

/** Texto seguro para pintar: sin saltos ni control, acotado. */
export function clean(text: unknown, limit = 80): string {
  if (text === null || text === undefined) return ''
  let s = String(text)
    .replace(/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/gu, ch => (ch === '‍' ? ch : ' '))
    .replace(/\s+/g, ' ')
    .trim()
  if ([...s].length > limit) s = [...s].slice(0, limit - 1).join('').trimEnd() + '…'
  return s
}

/** Redondeo a la par, como round() de Python: el % coincide con el del CLI. */
export function roundHalfEven(x: number): number {
  const f = Math.floor(x)
  const r = x - f
  if (r > 0.5) return f + 1
  if (r < 0.5) return f
  return f % 2 === 0 ? f : f + 1
}

/** ISO → ms. Una fecha ilegible cuenta como 0; una futura, como ahora. */
export function parseIso(s: unknown, now: number): number {
  const t = typeof s === 'string' ? Date.parse(s) : NaN
  return Number.isNaN(t) ? 0 : Math.min(t, now)
}

/** id = nombre del archivo; números y hijos del tipo que escribe el CLI. */
export function validFiche(d: unknown, stem: string): d is Json {
  if (!isObj(d) || d.id !== stem || !ID_RE.test(stem)) return false
  const it = d.iter
  const kids = d.children ?? {}
  const isRows = (v: unknown) => Array.isArray(v) && v.every(isObj)
  return (
    isInt(d.done ?? 0) &&
    isInt(d.total ?? 0) &&
    isRows(d.steps ?? []) &&
    isRows(d.plan ?? []) &&
    (it === null || it === undefined || (Array.isArray(it) && it.length === 2 && it.every(isInt))) &&
    typeof (d.cwd ?? '') === 'string' &&
    isObj(kids) &&
    Object.values(kids).every(isObj)
  )
}

/**
 * Lista de pasos: los cerrados (claves anteriores al historial primero, luego el historial)
 * y después los pendientes del plan. Lo que no tiene nombre se agrupa en una fila.
 */
export function stepRows(d: Json, t: Dict): StepRow[] {
  const rows = (v: unknown): Json[] => (Array.isArray(v) ? v.filter(isObj) : [])
  const kids = (d.children ?? {}) as Record<string, Json>
  const plan = rows(d.plan).filter(p => str(p.key) && str(p.label))
  const planLabel = new Map(plan.map(p => [str(p.key), clean(p.label)]))
  // Un paso del plan se llama como en el plan: la nota con que se cerró no lo renombra.
  const nameOf = (key: string, label: unknown): string =>
    planLabel.get(key) ||
    clean(label) ||
    (key.startsWith('child:') ? clean(kids[key.slice(6)]?.label, 40) || t.acceptedAgent : key)

  const history = rows(d.steps)
  const keys = (Array.isArray(d.keys) ? d.keys : []).filter((k): k is string => typeof k === 'string')
  const inHistory = new Set(history.map(h => str(h.key)).filter(Boolean))
  const closed = [
    ...keys.filter(k => !inHistory.has(k)).map(k => ({ key: k, label: nameOf(k, ''), at: '' })),
    ...history.map(h => ({ key: str(h.key), label: nameOf(str(h.key), h.label), at: str(h.at), ...tokOf(h.tok) })),
  ]
  const named = closed.filter(r => r.label !== '')
  const done = (d.done as number | undefined) ?? 0
  const unnamedDone = closed.length - named.length + Math.max(0, done - closed.length)

  const pending = plan.filter(p => !keys.includes(str(p.key)))
  const unnamedPending = Math.max(0, ((d.total as number | undefined) ?? 0) - done - pending.length)

  const out: StepRow[] = named.map(r => ({ ...r, isDone: true, isNamed: true }))
  if (unnamedDone > 0) out.push({ key: '', label: t.unnamedDone(unnamedDone), at: '', isDone: true, isNamed: false })
  out.push(...pending.map(p => ({ key: str(p.key), label: clean(p.label), at: '', isDone: false, isNamed: true })))
  if (unnamedPending > 0) {
    out.push({ key: '', label: t.unnamedPending(unnamedPending), at: '', isDone: false, isNamed: false })
  }
  return out
}

/** Cifra de tokens que guarda el CLI; nada si no se midió. */
function tokOf(v: unknown): { tok?: number } {
  return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? { tok: v } : {}
}

/** Ficha validada → la forma que guarda el mod (solo lo que se pinta). */
export function toFicha(d: Json, t: Dict): Ficha {
  const it = d.iter as [number, number] | null | undefined
  const kids = (d.children ?? {}) as Record<string, Json>
  const children: Child[] = Object.entries(kids)
    .filter(([, c]) => c.state === 'running' || c.state === 'delivered')
    .map(([cid, c]) => ({ label: clean(c.label || cid, 40), state: str(c.state), started: str(c.started) }))
  return {
    steps: stepRows(d, t),
    id: str(d.id),
    title: clean(d.title || d.id),
    cwd: str(d.cwd),
    done: (d.done as number | undefined) ?? 0,
    total: (d.total as number | undefined) ?? 0,
    iter: it ? [it[0], it[1]] : null,
    step: clean(d.step),
    status: str(d.status),
    started: str(d.started),
    updated: str(d.updated),
    owner: typeof d.owner === 'string' ? d.owner : null,
    children,
    ...planTokens(d.tokens),
    hidden: d.hidden === true,
    ...chatOf(d),
  }
}

const DESKTOP_ID = /^local_[0-9a-f-]{36}$/
const CLI_ID = /^[0-9a-f-]{36}$/

/** Cómo volver al último chat de la ficha. Sin el dato (fichas viejas), el de su dueña, por terminal. */
function chatOf(d: Json): { chat?: Ficha['chat'] } {
  const c = isObj(d.chat) ? d.chat : {}
  const id = str(c.id)
  if (c.app === 'desktop' && DESKTOP_ID.test(id)) return { chat: { app: 'desktop', id } }
  if (c.app === 'cli' && CLI_ID.test(id)) return { chat: { app: 'cli', id } }
  return typeof d.owner === 'string' && CLI_ID.test(d.owner) ? { chat: { app: 'cli', id: d.owner } } : {}
}

/** Total de tokens del plan (suma de sus tipos); nada si no se midió. */
function planTokens(v: unknown): { tokens?: number } {
  if (!isObj(v)) return {}
  const n = Object.values(v).reduce<number>((a, x) => a + (typeof x === 'number' && x > 0 ? x : 0), 0)
  return n > 0 ? { tokens: n } : {}
}

/** Contenido de _config.json → modo discreto. Config rota: fallar hacia el lado discreto. */
export function parseDiscreet(text: string | undefined): boolean {
  if (text === undefined) return false
  try {
    const cfg: unknown = JSON.parse(text.replace(/^﻿/, ''))
    return isObj(cfg) ? Boolean(cfg.discreet) : true
  } catch {
    return true
  }
}

export function pct(d: Ficha): number {
  if (d.total <= 0) return d.status === 'done' ? 100 : 0
  return Math.max(0, Math.min(100, roundHalfEven((100 * d.done) / d.total)))
}

export function glyph(p: number): string {
  return GLYPHS[p < 100 ? Math.min(4, Math.floor(p / 25)) : 4] ?? '○'
}

export function bar(p: number, width = 10): [string, string] {
  const full = roundHalfEven((p / 100) * width)
  return ['▓'.repeat(full), '░'.repeat(width - full)]
}

export const remaining = (d: Ficha) => Math.max(0, d.total - d.done)

export function staleAfter(d: Ficha): number {
  const r = remaining(d)
  return r > 0 && r <= 2 ? STALE_NEAR_END_MS : STALE_ACTIVITY_MS
}

export function isStale(d: Ficha, now: number): boolean {
  if (d.status !== 'active') return false
  if (d.children.some(c => c.state === 'running')) return false
  return now - parseIso(d.updated, now) > staleAfter(d)
}

/** «45 min», «1 h 12 min», «3 d». */
export function duration(ms: number, t: Dict): string {
  const m = Math.floor(Math.max(0, ms) / 60_000)
  if (m < 1) return t.lessThanMin
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`
  return `${Math.floor(h / 24)} d`
}

/** El paso en curso: el primer pendiente con nombre del plan. Sin plan no se sabe. */
export function currentStep(d: Ficha): string | undefined {
  return d.steps.find(r => !r.isDone && r.isNamed)?.label
}

/** El último paso cerrado con nombre; si la ficha no tiene lista, su campo `step`. */
export function lastClosed(d: Ficha): { label: string; at: string } | undefined {
  const row = [...d.steps].reverse().find(r => r.isDone && r.isNamed)
  if (row) return { label: row.label, at: row.at || d.updated }
  return d.step ? { label: d.step, at: d.updated } : undefined
}

/** Nombres de lo que falta, solo si todo lo que falta tiene nombre. */
export function pendingNames(d: Ficha): string[] | undefined {
  const named = d.steps.filter(r => !r.isDone && r.isNamed).map(r => r.label)
  return named.length === remaining(d) ? named : undefined
}

/** «paso 5 de 9»; con todo cerrado, «9/9 pasos». */
export function ordinal(d: Ficha, t: Dict): string {
  return d.done < d.total ? t.stepOf(d.done + 1, d.total) : t.stepsDone(d.done, d.total)
}

/** El paso que más tardó, por las horas del historial (el primero cuenta desde el arranque). */
export function longestStep(d: Ficha, now: number): { label: string; ms: number } | undefined {
  let prev = parseIso(d.started, now)
  let best: { label: string; ms: number } | undefined
  for (const r of d.steps) {
    if (!r.isDone || !r.at) continue
    const at = parseIso(r.at, now)
    if (prev > 0 && (!best || at - prev > best.ms)) best = { label: r.label, ms: at - prev }
    prev = at
  }
  return best
}

export type Tone = 'done' | 'current' | 'pending'

/**
 * La barra: un segmento por paso (━ cerrado, ┅ en curso, ─ pendiente) separados por un espacio;
 * si no caben en `budget` columnas o hay más de 20 pasos, una barra continua.
 */
export function segments(d: Ficha, budget: number): { text: string; tone: Tone }[] {
  const total = d.total
  if (total <= 0) return []
  const done = Math.min(d.done, total)
  const w = Math.min(4, Math.floor((budget - (total - 1)) / total))
  if (total > 20 || w < 1) {
    const full = roundHalfEven((done / total) * budget)
    return [
      { text: '━'.repeat(full), tone: 'done' as const },
      { text: '─'.repeat(budget - full), tone: 'pending' as const },
    ].filter(s => s.text)
  }
  return Array.from({ length: total }, (_, i) => {
    const tone: Tone = i < done ? 'done' : i === done ? 'current' : 'pending'
    const ch = tone === 'done' ? '━' : tone === 'current' ? '┅' : '─'
    return { text: ch.repeat(w) + (i < total - 1 ? ' ' : ''), tone }
  })
}

export function isAbandoned(d: Ficha, now: number): boolean {
  return d.status === 'paused' && now - parseIso(d.updated, now) > PAUSED_STALE_MS
}

export function childHung(c: Child, now: number): boolean {
  return c.state === 'running' && now - parseIso(c.started, now) > STALE_CHILD_MS
}

export function ago(ms: number, now: number, t: Dict): string {
  const s = Math.max(0, Math.floor((now - ms) / 1000))
  if (s < 60) return t.justNow
  if (s < 3600) return t.ago(`${Math.floor(s / 60)} min`)
  if (s < 86400) return t.ago(`${Math.floor(s / 3600)} h`)
  return t.ago(`${Math.floor(s / 86400)} d`)
}

/** Fichas cuyo cwd es cwd o un ancestro suyo: la más específica primero; a igualdad, la más reciente. */
export function forCwd(fichas: readonly Ficha[], cwd: string, now: number): Ficha[] {
  const rc = cwd.normalize('NFC')
  return fichas
    .filter(d => {
      const c = d.cwd.normalize('NFC').replace(/\/+$/, '')
      return d.status === 'active' && c !== '' && (rc === c || rc.startsWith(c + '/'))
    })
    .sort((a, b) => b.cwd.length - a.cwd.length || parseIso(b.updated, now) - parseIso(a.updated, now))
}

/**
 * La ficha de este chat (la más reciente si hay varias); si no tiene, una sin dueño de su carpeta
 * (creada fuera de Claude Code), la misma que el hook inyecta. Las de otros chats no salen en la banda.
 */
export function pickMine(s: Snap): Ficha | undefined {
  const owned = s.fichas.filter(d => d.status === 'active' && d.owner === s.sessionId)
  if (owned.length > 0) return owned.reduce((a, b) => (parseIso(b.updated, s.now) > parseIso(a.updated, s.now) ? b : a))
  return forCwd(s.fichas, s.cwd, s.now).find(d => d.owner === null)
}

/** Su chat tiene un turno en marcha: Claude está trabajando. */
export function isWorkingOn(d: Ficha, s: Snap): boolean {
  return d.owner !== null && s.working.includes(d.owner)
}

/** Parada de verdad: sin avance pasado el umbral, sin agentes y sin turno en marcha en su chat. */
export function isParada(d: Ficha, s: Snap, isWorking = false): boolean {
  return !isWorking && !isWorkingOn(d, s) && isStale(d, s.now)
}

/** En curso: activas antes que pausadas; dentro, la más reciente primero. */
export function live(s: Snap): Ficha[] {
  return s.fichas
    .filter(d => (d.status === 'active' || d.status === 'paused') && !d.hidden)
    .sort(
      (a, b) =>
        Number(a.status !== 'active') - Number(b.status !== 'active') ||
        parseIso(b.updated, s.now) - parseIso(a.updated, s.now),
    )
}

/** Las 00:00 de hoy, hora local. */
export function midnight(now: number): number {
  const t = new Date(now)
  t.setHours(0, 0, 0, 0)
  return t.getTime()
}

/** Cerradas hoy (terminadas o canceladas), la más reciente primero. */
export function finished(s: Snap): Ficha[] {
  return s.fichas
    .filter(d => (d.status === 'done' || d.status === 'cancelled') && !d.hidden && parseIso(d.updated, s.now) >= midnight(s.now))
    .sort((a, b) => parseIso(b.updated, s.now) - parseIso(a.updated, s.now))
}

/** Hijos vivos: colgados primero, luego por antigüedad. */
export function liveKids(d: Ficha, now: number): Child[] {
  return [...d.children].sort(
    (a, b) => Number(!childHung(a, now)) - Number(!childHung(b, now)) || parseIso(a.started, now) - parseIso(b.started, now),
  )
}

/** «iter 1/3 · 4/10 pasos» */
export function counts(d: Ficha, t: Dict): string {
  const parts = d.iter ? [`iter ${d.iter[0]}/${d.iter[1]}`] : []
  parts.push(t.stepsDone(d.done, d.total))
  return parts.join(' · ')
}

/** «● 2 agentes en curso · ◆ 1 por revisar», vacío sin hijos vivos. */
export function kidsSummary(d: Ficha, now: number, t: Dict): string {
  const running = d.children.filter(c => c.state === 'running')
  const hung = running.filter(c => childHung(c, now)).length
  const delivered = d.children.filter(c => c.state === 'delivered').length
  const parts: string[] = []
  if (running.length > 0) {
    parts.push(`● ${t.agentsRunning(running.length)}` + (hung ? ` (${t.agentsHung(hung)})` : ''))
  }
  if (delivered > 0) parts.push(`◆ ${t.toReview(delivered)}`)
  return parts.join(' · ')
}

/** Fichas de esta sesión que pasaron de activas a terminadas entre dos fotos. */
export function newlyDone(prev: Snap | null, next: Snap): Ficha[] {
  if (prev === null) return []
  const was = new Map(prev.fichas.map(d => [d.id, d.status]))
  return next.fichas.filter(d => d.status === 'done' && was.get(d.id) === 'active' && d.owner === next.sessionId)
}

/** Igualdad de fotos sin el reloj: el reloj solo cuenta por minutos. */
export function sameSnap(a: Snap | null, b: Snap): boolean {
  if (a === null) return false
  return JSON.stringify({ ...a, now: Math.floor(a.now / 60_000) }) === JSON.stringify({ ...b, now: Math.floor(b.now / 60_000) })
}
