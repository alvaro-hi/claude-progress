// Lógica pura de la 0.4.0: qué se enseña en cada nivel, el anillo y los hitos. Sin $ ni efectos.
import type { Ficha, Snap, StepRow } from '../types'
import { currentStep, duration, isParada, parseIso } from './lib'
import type { Dict } from './i18n'

export type Tone = 'work' | 'wait' | 'warn' | 'done'

export const FULL_MAX = 7 // hasta aquí se ven todos los pasos; por encima, ventana con lo oculto plegado
export const HUNG_MS = 60 * 60_000

const COLOR: Record<Tone, string> = { work: '#d97757', wait: '#a9a59c', warn: '#c27a12', done: '#2f9e5f' }
const SEG = '#dedad2'

/** Agentes que empujan el paso y lo que pide atención: el que no termina y las entregas por revisar. */
export function agentCounts(d: Ficha, now: number): { running: number; hung: number; review: number } {
  const running = d.children.filter(c => c.state === 'running')
  return {
    running: running.length,
    hung: running.filter(c => now - parseIso(c.started, now) > HUNG_MS).length,
    review: d.children.filter(c => c.state === 'delivered').length,
  }
}

/** «1 agente lleva más de 1 h · 2 entregas por revisar»; vacío si nada pide atención. */
export function attention(d: Ficha, now: number, t: Dict): string {
  const { hung, review } = agentCounts(d, now)
  const parts: string[] = []
  if (hung) parts.push(t.attentionHung(hung))
  if (review) parts.push(t.attentionReview(review))
  return parts.join(' · ')
}

/** Índice del paso en curso dentro de la lista (el primero sin cerrar). */
export function currentIndex(d: Ficha): number {
  const i = d.steps.findIndex(r => !r.isDone)
  return i < 0 ? d.steps.length : i
}

/**
 * Una sola lista por vista: hasta FULL_MAX pasos, todos; por encima, dos antes del actual,
 * el actual y dos después, con lo oculto plegado arriba y abajo (se abre en su sitio).
 */
export function stepWindow(d: Ficha, isFull: boolean): { before: StepRow[]; shown: StepRow[]; after: StepRow[] } {
  const rows = d.steps
  if (rows.length <= FULL_MAX || isFull) return { before: [], shown: rows, after: [] }
  const i = currentIndex(d)
  const lo = Math.max(0, i - 2)
  const hi = Math.min(rows.length, i + 3)
  return { before: rows.slice(0, lo), shown: rows.slice(lo, hi), after: rows.slice(hi) }
}

/** Lo que viene: el actual y los siguientes, para la vista previa. */
export function upcoming(d: Ficha, n = 3): string[] {
  return d.steps.filter(r => !r.isDone && r.isNamed).slice(0, n).map(r => r.label)
}

export function toneOf(d: Ficha, s: Snap, isWorking: boolean): Tone {
  if (d.status === 'done') return 'done'
  if (isParada(d, s, isWorking)) return 'warn'
  const busy = d.children.some(c => c.state === 'running')
  return isWorking || busy ? 'work' : 'wait'
}

/** El anillo por segmentos, en SVG: ≤12 con hueco, 13-30 hueco fino, >30 arco continuo; terminado, verde con check. */
export function ringSvg(total: number, done: number, size: number, stroke: number, tone: Tone, label = ''): string {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const col = COLOR[tone]
  const at = (extra: string) => `cx="${size / 2}" cy="${size / 2}" r="${r.toFixed(2)}" fill="none" stroke-width="${stroke}" ${extra}`
  const parts: string[] = [`<circle ${at(`stroke="${SEG}"`)}/>`]
  const h = Math.min(done, total)
  if (tone === 'done') {
    parts.push(`<circle ${at(`stroke="${col}"`)}/>`)
    const s = size
    parts.push(`<path d="M${(s * 0.33).toFixed(1)} ${(s * 0.52).toFixed(1)} L${(s * 0.45).toFixed(1)} ${(s * 0.63).toFixed(1)} L${(s * 0.68).toFixed(1)} ${(s * 0.38).toFixed(1)}" fill="none" stroke="${col}" stroke-width="${Math.max(2, stroke * 0.6).toFixed(1)}" stroke-linecap="round" stroke-linejoin="round"/>`)
  } else if (total > 30) {
    const arc = (c * h) / total
    parts.push(`<circle ${at(`stroke="${col}" stroke-dasharray="${arc.toFixed(2)} ${c.toFixed(2)}" stroke-dashoffset="${(c / 4).toFixed(2)}"`)}/>`)
  } else if (total > 0) {
    const gap = (total <= 12 ? 3.5 : 1.2) * (size / 46)
    const seg = (c - gap * total) / total
    for (let i = 0; i < total; i++) {
      const isCur = i === h && tone !== 'wait'
      const stroke_ = i < h || isCur ? col : SEG
      const op = isCur ? ' stroke-opacity="0.38"' : ''
      parts.push(`<circle ${at(`stroke="${stroke_}"${op} stroke-dasharray="${seg.toFixed(2)} ${(c - seg).toFixed(2)}" stroke-dashoffset="${(-(i * (seg + gap)) + c / 4).toFixed(2)}"`)}/>`)
    }
  }
  if (label && tone !== 'done') {
    const fs = label.length <= 3 ? size * 0.25 : size * 0.22
    parts.push(`<text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-weight="600" font-size="${fs.toFixed(1)}" fill="${tone === 'warn' ? COLOR.warn : tone === 'wait' ? '#7a776f' : '#1f1e1c'}">${label}</text>`)
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${parts.join('')}</svg>`
}

/** «h/t» dentro del anillo si cabe; si no, solo los hechos. */
export function ringLabel(d: Ficha): string {
  if (d.total <= 0) return '—'
  const l = `${d.done}/${d.total}`
  return l.length > 5 ? String(d.done) : l
}

/** El anillo en terminal: cuarto de círculo según el avance. */
export function ringGlyph(d: Ficha): string {
  if (d.status === 'done') return '✓'
  if (d.total <= 0) return '○'
  const f = d.done / d.total
  return f >= 1 ? '●' : f >= 0.75 ? '◕' : f >= 0.5 ? '◑' : f > 0 ? '◔' : '○'
}

// ── Hitos en la conversación ──────────────────────────────────────────────

export type Call = { verb: 'step' | 'accept' | 'done' | 'start' | 'plan'; id: string; label: string; key: string }

const ID = '([a-z0-9][a-z0-9._-]{0,63})'
const VAR_RE = /(\w+)=["']?[^\s;&|"']*\/progress["']?(?=[\s;&|]|$)/g

/** Las llamadas a `progress` de un comando de Bash que dejan hito, en orden; también vía variable (P=…/progress; $P step x). */
export function parseCalls(command: string): Call[] {
  const heads = ['(?:^|[\\s/;&|(])progress', ...[...command.matchAll(VAR_RE)].map(m => `\\$\\{?${m[1]}\\}?`)]
  const re = new RegExp(
    `(?:${heads.join('|')})\\s+(?:(step|done|start|plan)\\s+${ID}|child\\s+accept\\s+${ID}\\s+(\\S+))([^;&|]*)`,
    'g',
  )
  const out: Call[] = []
  for (const m of command.matchAll(re)) {
    const verb = (m[1] ?? 'accept') as Call['verb']
    const id = m[2] ?? m[3] ?? ''
    const rest = m[5] ?? ''
    const label = /^\s*(?:"([^"]*)"|'([^']*)')/.exec(rest)
    const key = /--key\s+(\S+)/.exec(rest)?.[1] ?? (verb === 'accept' ? `child:${m[4]}` : '')
    out.push({ verb, id, label: label?.[1] ?? label?.[2] ?? '', key })
  }
  return out
}

/** «mod-040 · 3/6 · 50%» en la salida del CLI → hechos y total en ese momento. */
export function countsAt(stdout: string, id: string): { done: number; total: number } | undefined {
  const re = new RegExp(`^${id.replace(/[.]/g, '\\.')} · (\\d+)/(\\d+)`, 'gm')
  let last: RegExpExecArray | null = null
  for (let m = re.exec(stdout); m; m = re.exec(stdout)) last = m
  return last ? { done: Number(last[1]), total: Number(last[2]) } : undefined
}

/** ¿La salida es solo del CLI? Entonces la fila de resultado sobra: el hito ya lo cuenta. */
export function isProgressOutput(stdout: string): boolean {
  const lines = stdout.split('\n').filter(l => l.trim())
  return lines.length > 0 && lines.every(l => /^[a-z0-9][a-z0-9._-]* · \d+\/\d+ · \d+%/.test(l))
}

export type Milestone = {
  ficha: Ficha
  kind: 'step' | 'done' | 'plan'
  closed: string
  next: string | undefined
  done: number
  total: number
  isLatest: boolean
}

/** El hito que deja un comando: qué se cerró, qué venía después y si es el último de su ficha. */
export function milestoneOf(command: string, stdout: string, s: Snap, t: Dict): Milestone | undefined {
  const calls = parseCalls(command)
  const last = calls.at(-1)
  if (!last) return undefined
  const ficha = s.fichas.find(f => f.id === last.id)
  if (!ficha) return undefined
  const at = countsAt(stdout, ficha.id) ?? { done: ficha.done, total: ficha.total }
  const isLatest = at.done === ficha.done
  if (last.verb === 'done') {
    return { ficha, kind: 'done', closed: '', next: undefined, done: at.done, total: at.total, isLatest }
  }
  if (last.verb === 'start' || last.verb === 'plan') {
    return { ficha, kind: 'plan', closed: '', next: currentStep(ficha), done: at.done, total: at.total, isLatest }
  }
  const byKey = last.key ? ficha.steps.find(r => r.isDone && r.key === last.key) : undefined
  const closed = byKey?.label || last.label || ficha.step || t.stepClosed
  const next = isLatest ? currentStep(ficha) : ficha.steps[at.done]?.label
  return { ficha, kind: 'step', closed, next, done: at.done, total: at.total, isLatest }
}

/** «9 pasos en 1 h 12 min». */
export function tookText(d: Ficha, now: number, t: Dict): string {
  const took = t.took(t.steps(d.done), duration(parseIso(d.updated, now) - parseIso(d.started, now), t))
  return d.tokens ? `${took} · ${tokText(d.tokens, t)}` : took
}

/** «850 tokens», «12 k tokens», «1,2 M tokens» (en inglés, «12k tokens», «1.2M tokens»). */
export function tokText(n: number, t: Dict): string {
  return t.tokens(n)
}
