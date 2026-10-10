// Hitos en la conversación (todas las superficies, el móvil incluido): el Bash que ejecuta `progress step`
// se dibuja como «Ahora: X · ✓ lo cerrado · N/M»; un grupo plegado que lo contiene, igual, con su cuenta.
import type { RenderChildren } from 'claude-code'

import type { Snap } from '../types'
import { milestoneOf, tookText } from './view'
import type { Milestone } from './view'
import { dim, nameOf, ring } from './shared'
import type { Actions, El } from './shared'

export function stdoutOf(output: unknown): string {
  if (typeof output === 'string') return output
  if (output && typeof output === 'object' && 'stdout' in output) {
    const v = (output as { stdout: unknown }).stdout
    return typeof v === 'string' ? v : ''
  }
  return ''
}

export function commandOf(input: unknown): string {
  if (input && typeof input === 'object' && 'command' in input) {
    const v = (input as { command: unknown }).command
    return typeof v === 'string' ? v : ''
  }
  return ''
}

/** Las dos líneas del hito, según qué cerró la llamada y si es la última de su ficha. */
function lines(T: El, m: Milestone, s: Snap): { main: string; sub: string; tone: 'work' | 'done' } {
  const { t } = T
  const name = nameOf(T, m.ficha, s)
  const closed = s.discreet ? t.stepRef(m.done) : m.closed
  const next = s.discreet ? undefined : m.next
  if (m.kind === 'done') return { main: `${name} · ${t.finished}`, sub: tookText(m.ficha, s.now, t), tone: 'done' }
  if (m.kind === 'plan') {
    return { main: t.planHead(name), sub: t.planSub(m.total, next), tone: 'work' }
  }
  if (m.isLatest && next) return { main: t.nowHead(next), sub: `✓ ${closed} · ${m.done}/${m.total}`, tone: 'work' }
  return { main: `✓ ${closed}`, sub: `${m.done}/${m.total}${next ? ` · ${t.thenInline(next)}` : ''}`, tone: 'work' }
}

export function mileRow(T: El, m: Milestone, s: Snap, key: string, act: Actions, extra?: RenderChildren) {
  const { Box, Text, Button } = T
  const { main, sub, tone } = lines(T, m, s)
  const shown = { ...m.ficha, done: m.done, total: m.total }
  return (
    <Box key={key} flexDirection="column">
      <Box flexDirection="row" gap={1} alignItems="center">
        {ring(T, shown, tone, 22, 3, false)}
        <Box flexDirection="column" flexGrow={1} flexShrink={1}>
          <Text bold {...(tone === 'done' ? { color: 'success' as const } : {})} wrap="truncate-end">
            {main}
          </Text>
          <Text {...dim} wrap="truncate-end">
            {sub}
          </Text>
        </Box>
        <Button key={`${key}-abrir`} label={T.t.openProgress} plain dimColor onPress={() => act.openPanel(m.ficha.id)} />
      </Box>
      {extra}
    </Box>
  )
}

export function unfoldButton(T: El, key: string, count: number, act: Actions) {
  const { Button } = T
  return (
    <Button
      key={`${key}-ver`}
      label={`▸ ${T.t.showCommands(count)}`}
      plain
      dimColor
      onPress={() => act.unfold(key)}
    />
  )
}

export { milestoneOf }
