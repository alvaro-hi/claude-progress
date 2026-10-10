// Banda B (terminal y escritorio): anillo con la cifra, el paso actual arriba, el plan y el pulso debajo.
// Pasar el ratón despliega «Luego: …» en su sitio (estilo, sin coste); ▸ la fija con la lista de pasos. Dibujo puro.
import type { Color } from 'claude-code'

import type { Ficha, Snap } from '../types'
import { ago, currentStep, duration, lastClosed, longestStep, parseIso, pendingNames, pickMine } from './lib'
import { agentCounts, tookText, toneOf, upcoming } from './view'
import type { Tone } from './view'
import { dim, level1, nameOf, ring } from './shared'
import type { Actions, El, UiState } from './shared'

/** El pulso: lo último cerrado y cuándo, o cerca del final lo que falta; y los agentes en marcha. */
function pulse(T: El, d: Ficha, s: Snap): string {
  const { t } = T
  const parts: string[] = []
  const left = pendingNames(d)
  const last = lastClosed(d)
  if (left && left.length > 0 && left.length <= 2) {
    parts.push(`${t.left(left.length)}${s.discreet ? '' : `: ${left.join(' · ')}`}`)
    parts.push(ago(parseIso(d.updated, s.now), s.now, t))
  } else if (last) {
    const when = ago(parseIso(last.at, s.now), s.now, t)
    parts.push(s.discreet ? `✓ ${when}` : `✓ ${last.label} · ${when}`)
  } else {
    parts.push(ago(parseIso(d.updated, s.now), s.now, t))
  }
  const run = agentCounts(d, s.now).running
  if (run) parts.push(t.agents(run))
  return parts.join(' · ')
}

function closingBand(T: El, d: Ficha, s: Snap) {
  const { Box, Text, t } = T
  const longest = d.steps.filter(r => r.isDone && r.at).length >= 3 ? longestStep(d, s.now) : undefined
  const extra = longest
    ? ` · ${s.discreet ? t.longestStepAnon(duration(longest.ms, t)) : t.longestNamed(longest.label, duration(longest.ms, t))}`
    : ''
  return (
    <Box flexDirection="row" gap={1} alignItems="center">
      {ring(T, d, 'done', 46, 6.5, false)}
      <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0}>
        <Text bold color="success" wrap="truncate-end">
          {`${nameOf(T, d, s)} · ${t.finished}`}
        </Text>
        <Text dimColor wrap="truncate-end">
          {tookText(d, s.now, t) + extra}
        </Text>
      </Box>
    </Box>
  )
}

export function drawBand(T: El, s: Snap, isWorking: boolean, ui: UiState, act: Actions) {
  const { Box, Text, Button, t } = T

  const closingId = ui.closing
  const ended = closingId ? s.fichas.find(f => f.id === closingId && f.status === 'done') : undefined
  if (ended) return closingBand(T, ended, s)

  const d = pickMine(s)
  if (!d) return undefined
  const tone: Tone = toneOf(d, s, isWorking)
  const name = nameOf(T, d, s)
  const step = s.discreet ? undefined : currentStep(d)
  const pinned = ui.pinned
  const pin = (
    <Box flexShrink={0}>
      <Button key="fijar" label={pinned ? '▾' : '▸'} plain dimColor onPress={act.togglePin} />
    </Box>
  )

  // Fijada: la cabecera pasa a ser el plan; el paso actual vive solo en la lista.
  if (pinned) {
    const { full } = ui
    return (
      <Box key="banda" flexDirection="column">
        <Box flexDirection="row" gap={1} alignItems="center">
          {ring(T, d, tone, 46, 6.5, true)}
          <Box flexGrow={1} flexShrink={1} minWidth={0}>
            <Text bold wrap="wrap">
              {name}
            </Text>
          </Box>
          <Box flexShrink={0}>
            <Button key="panel" label={t.panelButton} plain dimColor onPress={() => act.openPanel(d.id)} />
          </Box>
          {pin}
        </Box>
        <Box paddingLeft={8} flexDirection="column">
          {level1(T, d, s, tone, full.includes(d.id), act)}
        </Box>
      </Box>
    )
  }

  let line1: string
  let line2: string
  let color1: { color?: Color; dimColor?: boolean } = {}
  if (tone === 'warn') {
    line1 = t.stalled(step ?? name, duration(s.now - parseIso(d.updated, s.now), t))
    line2 = name
    color1 = { color: 'warning' }
  } else if (tone === 'wait') {
    line1 = name
    line2 = `${t.waitingForYou}${step ? ` · ${t.nowInline(step)}` : ''}`
    color1 = dim
  } else {
    line1 = step ?? name
    line2 = `${step ? `${name} · ` : ''}${pulse(T, d, s)}`
  }
  const next = s.discreet ? [] : upcoming(d).slice(step ? 1 : 0)
  return (
    <Box key="banda" flexDirection="column">
      <Box flexDirection="row" gap={1} alignItems="center">
        {ring(T, d, tone, 46, 6.5, true)}
        <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0}>
          <Text bold {...color1} wrap="truncate-end">
            {line1}
          </Text>
          <Text dimColor wrap="truncate-end">
            {line2}
          </Text>
          {next.length > 0 && (
            <Box display="none" hover={{ display: 'flex' }}>
              <Text dimColor wrap="truncate-end">
                {t.thenHead(next.join(' → '))}
              </Text>
            </Box>
          )}
        </Box>
        {pin}
      </Box>
    </Box>
  )
}
