// Estado y piezas de dibujo puras que comparten banda, panel e hitos. Nada aquí toca el motor:
// el validador solo lo sigue dentro de register.tsx, así que las acciones llegan ya hechas.
import type { BoxProps, ButtonProps, Color, ElementConstructor, RenderSurface, SvgProps, TextProps } from 'claude-code'

import type { Ficha, Snap, StepRow } from '../types'
import { ago, parseIso } from './lib'
import { agentCounts, attention, ringGlyph, ringLabel, ringSvg, stepWindow, tokText } from './view'
import type { Tone } from './view'
import type { Dict } from './i18n'

export const PANE = 'progress'

export type El = {
  /** la superficie: en terminal no hay SVG (la tabla lo completa con un fragmento vacío) */
  surface: string
  /** los textos en el idioma resuelto por register.tsx */
  t: Dict
  Box: ElementConstructor<BoxProps>
  Text: ElementConstructor<TextProps>
  Button: ElementConstructor<ButtonProps>
  Svg?: ElementConstructor<SvgProps>
}

export const TINT: Record<Tone, Color> = { work: 'claude', wait: 'subtle', warn: 'warning', done: 'success' }
export const dim = { dimColor: true } as const

export type Actions = {
  toggleOpen: (id: string) => unknown
  toggleFull: (id: string) => unknown
  /** fuera de la lista hasta que el plan se mueva; no toca el trabajo */
  hide: (id: string) => unknown
  /** las cerradas a _done/ */
  clear: () => unknown
  /** al último chat del plan: lo abre en la app de escritorio o copia `claude --resume <id>` */
  goChat: (d: Ficha, surface: RenderSurface) => unknown
  openPanel: (id: string) => unknown
  togglePin: () => unknown
  discreet: () => unknown
  close: () => unknown
  unfold: (key: string) => unknown
}

export type UiState = {
  open: string[]
  full: string[]
  pinned: boolean
  groups: string[]
  closing: string | null
}

export function toggleIn(list: readonly string[], id: string): string[] {
  return list.includes(id) ? list.filter(x => x !== id) : [...list, id]
}

export const nameOf = (T: El, d: Ficha, s: Snap) => (s.discreet ? T.t.activity : d.title)

/** El anillo: SVG donde hay dibujo; en terminal, un cuarto de círculo y la cifra. */
export function ring(T: El, d: Ficha, tone: Tone, size: number, stroke: number, withLabel: boolean) {
  const label = withLabel ? ringLabel(d) : ''
  if (T.surface !== 'terminal' && T.Svg) {
    const Svg = T.Svg
    return (
      <Svg
        source={ringSvg(d.total, d.done, size, stroke, tone, label)}
        alt={d.status === 'done' ? T.t.finished : T.t.ringAlt(d.done, d.total)}
        width={size}
        height={size}
      />
    )
  }
  const { Text } = T
  return <Text color={TINT[tone]}>{withLabel ? `${ringGlyph(d)} ${label}` : ringGlyph(d)}</Text>
}

/** Una fila de la lista de pasos. El actual lleva pegados sus agentes; en ámbar si está parado. */
function stepLine(T: El, d: Ficha, s: Snap, r: StepRow, i: number, isCur: boolean, tone: Tone) {
  const { Box, Text, t } = T
  const label = s.discreet && r.isNamed ? t.stepLabel(i + 1) : r.label
  const run = isCur ? agentCounts(d, s.now).running : 0
  const when = r.isDone ? [r.tok ? tokText(r.tok, t) : '', r.at ? ago(parseIso(r.at, s.now), s.now, t) : ''].filter(Boolean).join(' · ') : ''
  const glyph = r.isDone ? '✓' : isCur ? '●' : '○'
  const gcol: Color = r.isDone ? 'success' : isCur ? (tone === 'warn' ? 'warning' : 'claude') : 'subtle'
  return (
    <Box key={`paso-${d.id}-${i}`} flexDirection="row" gap={1}>
      <Text color={gcol}>{glyph}</Text>
      <Box flexDirection="row" flexGrow={1} flexShrink={1}>
        <Text bold={isCur} {...(r.isDone ? dim : {})} wrap="wrap">
          {label}
        </Text>
        {run > 0 && <Text color="claude">{` · ${t.agents(run)}`}</Text>}
      </Box>
      {when && <Text dimColor>{when}</Text>}
    </Box>
  )
}

/**
 * Asomarse: una sola lista de pasos (todos hasta 7; si no, ventana con lo oculto plegado en su sitio)
 * y lo que pide atención. Sin acciones sobre el plan: pararlo o retomarlo es cosa del chat.
 * Lo comparten la fila del panel y la banda fijada.
 */
export function level1(T: El, d: Ficha, s: Snap, tone: Tone, isFull: boolean, act: Actions) {
  const { Box, Text, Button, t } = T
  const { before, shown, after } = stepWindow(d, isFull)
  const cur = d.steps.findIndex(r => !r.isDone)
  const offset = before.length
  const toggleFull = () => act.toggleFull(d.id)
  const warn = attention(d, s.now, t)
  return (
    <Box flexDirection="column">
      {before.length > 0 && (
        <Button key={`antes-${d.id}`} label={`▸ ${t.stepsBefore(before.length)}`} plain dimColor onPress={toggleFull} />
      )}
      {shown.map((r, i) => stepLine(T, d, s, r, offset + i, offset + i === cur, tone))}
      {after.length > 0 && <Button key={`despues-${d.id}`} label={`▸ ${t.andMore(after.length)}`} plain dimColor onPress={toggleFull} />}
      {isFull && d.steps.length > 7 && <Button key={`plegar-${d.id}`} label={`▴ ${t.fold}`} plain dimColor onPress={toggleFull} />}
      {warn && <Text color="warning">{`◆ ${warn}`}</Text>}
    </Box>
  )
}
