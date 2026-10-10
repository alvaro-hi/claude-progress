// Panel P por secciones: «En este chat» (sus planes en curso y los que ha cerrado hoy), «Otros planes
// en curso» (por quién tiene que moverse: te esperan, trabajan, parados, en pausa) y «Terminadas hoy».
// Filas tipo Linear: anillo · plan · paso actual · N/M; el estado solo si es una excepción.
// El único mando sobre un plan es «Ocultar» (fuera de la lista hasta que se mueva); «Vaciar» limpia
// todas las cerradas: junto a «Terminadas hoy en otros chats» o, si solo hay de este chat, a «En este chat». Parar o retomar un plan es cosa de su chat.
import type { Color } from 'claude-code'

import type { Ficha, Snap } from '../types'
import { clean, duration, finished, isAbandoned, isParada, isWorkingOn, live, longestStep, parseIso } from './lib'
import { agentCounts, tookText } from './view'
import type { Tone } from './view'
import { dim, level1, nameOf, ring } from './shared'
import type { Actions, El, UiState } from './shared'

const FIN_SHOWN = 3 // terminadas a la vista; el resto tras «▸ y N más»
const FIN_KEY = 'terminadas' // en `full`: la lista de terminadas abierta entera

/** Estado en palabra, solo para las excepciones. */
function stateOf(T: El, d: Ficha, s: Snap): { word: string; tone: Tone; color: Color } | undefined {
  const { t } = T
  if (isParada(d, s)) return { word: t.stalledState(duration(s.now - parseIso(d.updated, s.now), t)), tone: 'warn', color: 'warning' }
  if (d.status === 'paused') return { word: t.paused, tone: 'wait', color: 'subtle' }
  return undefined
}

const isBusy = (d: Ficha, s: Snap) => isWorkingOn(d, s) || agentCounts(d, s.now).running > 0
const waitsForYou = (d: Ficha, s: Snap) => d.status === 'active' && !isBusy(d, s) && !isParada(d, s)

/** Subtítulo de la fila cerrada: si te espera, el paso actual y sus agentes. */
function subOf(T: El, d: Ficha, s: Snap, isMine: boolean): string {
  const { t } = T
  const cur = s.discreet ? undefined : d.steps.find(r => !r.isDone)?.label
  if (isAbandoned(d, s.now)) return t.pausedFor(duration(s.now - parseIso(d.updated, s.now), t))
  const run = agentCounts(d, s.now).running
  const waiting = !isMine && waitsForYou(d, s) ? t.waitingForYou : ''
  return [waiting, cur ?? '', run ? t.agents(run) : ''].filter(Boolean).join(' · ')
}

/** Otros planes: primero los que te esperan, luego los que trabajan, los parados y los pausados. */
function rank(d: Ficha, s: Snap): number {
  if (d.status === 'paused') return 3
  if (isParada(d, s)) return 2
  return isBusy(d, s) ? 1 : 0
}

function row(T: El, d: Ficha, s: Snap, isOpen: boolean, isFull: boolean, isMine: boolean, act: Actions) {
  const { Box, Text, Button, t } = T
  const st = stateOf(T, d, s)
  const tone: Tone = st?.tone ?? (isBusy(d, s) ? 'work' : 'wait')
  const sub = subOf(T, d, s, isMine)
  return (
    <Box key={`fila-${d.id}`} flexDirection="column" paddingY={1}>
      <Box flexDirection="row" gap={1} alignItems="center">
        {ring(T, d, tone, 18, 3, false)}
        <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0}>
          {/* el título parte línea, nunca se recorta: recortado, el escritorio no le cede sitio a los mandos */}
          <Text bold={isMine || isOpen} wrap="wrap">
            {nameOf(T, d, s)}
          </Text>
          {!isOpen && sub && (
            <Text {...dim} wrap="truncate-end">
              {sub}
            </Text>
          )}
        </Box>
        <Box flexDirection="column" alignItems="flex-end" flexShrink={0}>
          {st && <Text color={st.color}>{st.word}</Text>}
          <Text dimColor>{`${d.done}/${d.total}`}</Text>
        </Box>
        {/* los mandos nunca se recortan: cede el título */}
        <Box flexDirection="row" gap={1} flexShrink={0}>
          <Button key={`abrir-${d.id}`} label={isOpen ? '▾' : '▸'} plain dimColor onPress={() => act.toggleOpen(d.id)} />
          {!isMine && d.chat && <Button key={`chat-${d.id}`} label={t.goToChat} plain dimColor onPress={e => act.goChat(d, e.surface)} />}
          {!isMine && <Button key={`ocultar-${d.id}`} label={t.hide} plain dimColor onPress={() => act.hide(d.id)} />}
        </Box>
      </Box>
      {isOpen && (
        <Box paddingLeft={3} flexDirection="column">
          {level1(T, d, s, tone, isFull, act)}
        </Box>
      )}
    </Box>
  )
}

function finishedRow(T: El, d: Ficha, s: Snap, isMine: boolean, act: Actions) {
  const { Box, Text, Button, t } = T
  const cancelled = d.status === 'cancelled'
  const longest = !cancelled && d.steps.filter(r => r.isDone && r.at).length >= 3 ? longestStep(d, s.now) : undefined
  const extra = longest
    ? ` · ${s.discreet ? t.longestAnon(duration(longest.ms, t)) : t.longestNamed(longest.label, duration(longest.ms, t))}`
    : ''
  const line = cancelled ? t.cancelledAt(d.done, d.total) : tookText(d, s.now, t) + extra
  return (
    <Box key={`fin-${d.id}`} flexDirection="row" gap={1} alignItems="center" paddingY={1}>
      {cancelled ? <Text dimColor>–</Text> : ring(T, d, 'done', 18, 3, false)}
      <Box flexDirection="column" flexGrow={1} flexShrink={1}>
        <Text {...(isMine ? dim : {})} wrap="truncate-end">
          {nameOf(T, d, s)}
        </Text>
        <Text dimColor wrap="wrap">
          {line}
        </Text>
      </Box>
      {!isMine && d.chat && (
        <Box flexShrink={0}>
          <Button key={`chat-${d.id}`} label={t.goToChat} plain dimColor onPress={e => act.goChat(d, e.surface)} />
        </Box>
      )}
    </Box>
  )
}

export function drawPane(T: El, s: Snap | null, ui: UiState, act: Actions) {
  const { Box, Text, Button, t } = T
  if (!s) return <Text dimColor>{t.loading}</Text>
  const { open, full } = ui
  const all = live(s)
  const fin = finished(s)
  const mineLive = all.filter(d => d.owner === s.sessionId)
  const mineFin = fin.filter(d => d.owner === s.sessionId)
  const others = all
    .filter(d => d.owner !== s.sessionId)
    .sort((a, b) => rank(a, s) - rank(b, s) || parseIso(b.updated, s.now) - parseIso(a.updated, s.now))
  const otherFin = fin.filter(d => d.owner !== s.sessionId)
  const finOpen = full.includes(FIN_KEY)
  const finShown = finOpen ? otherFin : otherFin.slice(0, FIN_SHOWN)
  const rowOf = (d: Ficha, isMine: boolean) => row(T, d, s, open.includes(d.id), full.includes(d.id), isMine, act)
  const vaciar = <Button key="vaciar" label={t.clear} plain dimColor onPress={act.clear} />
  const empty = mineLive.length + mineFin.length + others.length + otherFin.length === 0
  return (
    <Box flexDirection="column">
      {empty && <Text dimColor>{t.noPlans}</Text>}
      {mineLive.length + mineFin.length > 0 && (
        <Box key="sec-chat" flexDirection="column">
          <Box flexDirection="row" gap={1}>
            <Box flexGrow={1}>
              <Text dimColor>{t.secThisChat}</Text>
            </Box>
            {/* sin terminadas de otros chats, «Vaciar» va junto a la sección que sí las tiene */}
            {otherFin.length === 0 && mineFin.length > 0 && vaciar}
          </Box>
          {mineLive.map(d => rowOf(d, true))}
          {mineFin.map(d => finishedRow(T, d, s, true, act))}
        </Box>
      )}
      {others.length > 0 && (
        <Box key="sec-otros" flexDirection="column" marginTop={1}>
          <Text dimColor>{t.secOthers}</Text>
          {others.map(d => rowOf(d, false))}
        </Box>
      )}
      {s.bad.map(b => (
        <Text key={`ilegible-${b}`} color="warning">{`◆ ${t.unreadable(s.discreet ? '?' : clean(b, 40))}`}</Text>
      ))}
      {otherFin.length > 0 && (
        <Box key="sec-fin" flexDirection="column" marginTop={1}>
          <Box flexDirection="row" gap={1}>
            <Box flexGrow={1}>
              <Text dimColor>{t.secFinished}</Text>
            </Box>
            {vaciar}
          </Box>
          {finShown.map(d => finishedRow(T, d, s, false, act))}
          {otherFin.length > FIN_SHOWN && (
            <Button
              key="terminadas-mas"
              label={finOpen ? `▴ ${t.fold}` : `▸ ${t.andMore(otherFin.length - FIN_SHOWN)}`}
              plain
              dimColor
              onPress={() => act.toggleFull(FIN_KEY)}
            />
          )}
        </Box>
      )}
      <Box flexDirection="row" gap={1} marginTop={1}>
        <Button key="discreto" label={t.discreetMode(s.discreet)} plain dimColor onPress={act.discreet} />
        <Button key="cerrar" role="dismiss" label={t.close} onPress={act.close} />
      </Box>
    </Box>
  )
}
