// Textos de la interfaz en inglés y español. Puro: sin $ ni efectos. register.tsx resuelve el idioma
// (ajuste `language` del plugin; en `auto`, el locale del entorno) y pasa el diccionario a las piezas de dibujo.

export type Lang = 'en' | 'es'

const LANGS: readonly Lang[] = ['en', 'es']

/**
 * El idioma a usar: `en` o `es` fijados en el ajuste ganan; si no (`auto`, vacío o desconocido),
 * el locale del entorno: es* → español; cualquier otro, o ninguno, → inglés.
 */
export function pickLang(setting: unknown, envLang: string | undefined): Lang {
  if (typeof setting === 'string' && (LANGS as readonly string[]).includes(setting)) return setting as Lang
  return /^es([_.@-]|$)/i.test((envLang ?? '').trim()) ? 'es' : 'en'
}

/** El locale que manda, como en POSIX: LC_ALL, luego LC_MESSAGES, luego LANG; el primero no vacío. */
export function envLocale(lcAll?: string, lcMessages?: string, lang?: string): string | undefined {
  return [lcAll, lcMessages, lang].find(v => typeof v === 'string' && v.trim() !== '')
}

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** «850 tokens», «12 k tokens», «1,2 M tokens» (separador decimal y espaciado según el idioma). */
function tokens(n: number, sep: string, gap: string): string {
  if (n < 1000) return `${Math.round(n)} tokens`
  if (n < 1_000_000) return `${Math.round(n / 1000)}${gap}k tokens`
  return `${(Math.round(n / 100_000) / 10).toString().replace('.', sep)}${gap}M tokens`
}

const es = {
  // registro, comando y avisos
  paneTitle: 'Progreso',
  commandDescription: 'Abre el panel con todas las fichas de progreso (~/.claude/progress)',
  paneOpened: (n: number) => `Panel de progreso abierto: ${n} en curso.`,
  paneWaiting: 'El panel de progreso espera sitio: ensancha la ventana o cierra otro panel.',
  exitedWith: (code: number) => `salió con ${code}`,
  hiddenToast: 'Oculta · vuelve si el plan avanza',
  chatOpenFailed: 'no se pudo abrir el chat',
  resumeCopied: 'Copiado: pégalo en un terminal para volver a ese chat',
  // tiempos y cifras
  lessThanMin: 'menos de 1 min',
  justNow: 'hace un momento',
  ago: (span: string) => `hace ${span}`,
  tokens: (n: number) => tokens(n, ',', ' '),
  // pasos y agentes
  activity: 'Actividad',
  agents: (n: number) => count(n, 'agente', 'agentes'),
  steps: (n: number) => count(n, 'paso', 'pasos'),
  stepLabel: (i: number) => `Paso ${i}`,
  stepRef: (i: number) => `paso ${i}`,
  stepOf: (i: number, total: number) => `paso ${i} de ${total}`,
  stepsDone: (done: number, total: number) => `${done}/${total} pasos`,
  unnamedDone: (n: number) => count(n, 'paso sin nombre', 'pasos sin nombre'),
  unnamedPending: (n: number) => count(n, 'paso pendiente sin nombre', 'pasos pendientes sin nombre'),
  acceptedAgent: 'agente aceptado',
  stepClosed: 'paso cerrado',
  agentsRunning: (n: number) => `${count(n, 'agente', 'agentes')} en curso`,
  agentsHung: (n: number) => `${n} ¿colgado?`,
  toReview: (n: number) => `${n} por revisar`,
  attentionHung: (n: number) => `${count(n, 'agente', 'agentes')} ${n === 1 ? 'lleva' : 'llevan'} más de 1 h`,
  attentionReview: (n: number) => count(n, 'entrega por revisar', 'entregas por revisar'),
  // anillo y lista
  finished: 'terminado',
  ringAlt: (done: number, total: number) => `${done} de ${total} pasos`,
  stepsBefore: (n: number) => count(n, 'paso antes', 'pasos antes'),
  andMore: (n: number) => `y ${n} más`,
  fold: 'plegar',
  // banda e hitos
  took: (steps: string, dur: string) => `${steps} en ${dur}`,
  left: (n: number) => (n === 1 ? 'falta 1' : `faltan ${n}`),
  longestStepAnon: (dur: string) => `el paso más largo: ${dur}`,
  longestAnon: (dur: string) => `el más largo: ${dur}`,
  longestNamed: (label: string, dur: string) => `el más largo: ${label} (${dur})`,
  stalled: (what: string, dur: string) => `${what} lleva ${dur} sin avance`,
  waitingForYou: 'esperando tu respuesta',
  nowInline: (step: string) => `ahora: ${step}`,
  nowHead: (step: string) => `Ahora: ${step}`,
  thenHead: (steps: string) => `Luego: ${steps}`,
  thenInline: (step: string) => `luego: ${step}`,
  panelButton: 'panel',
  planHead: (name: string) => `Plan: ${name}`,
  planSub: (total: number, first?: string) => `${total} pasos${first ? ` · empieza por ${first}` : ''}`,
  openProgress: 'Abrir progreso',
  showCommands: (n: number) => (n === 1 ? 'ver el comando' : `ver los ${n} comandos`),
  // panel
  stalledState: (dur: string) => `Parada · ${dur}`,
  paused: 'En pausa',
  pausedFor: (dur: string) => `en pausa desde hace ${dur}`,
  goToChat: 'Ir al chat',
  hide: 'Ocultar',
  clear: 'Vaciar',
  close: 'Cerrar',
  cancelledAt: (done: number, total: number) => `cancelada con ${done}/${total}`,
  loading: 'Leyendo fichas…',
  noPlans: 'Sin planes.',
  secThisChat: 'EN ESTE CHAT',
  secOthers: 'OTROS PLANES EN CURSO',
  secFinished: 'TERMINADAS HOY EN OTROS CHATS',
  unreadable: (name: string) => `ficha ilegible: ${name}`,
  discreetMode: (on: boolean) => `Modo discreto: ${on ? 'sí' : 'no'}`,
}

export type Dict = typeof es

const en: Dict = {
  paneTitle: 'Progress',
  commandDescription: 'Open the panel with every progress card (~/.claude/progress)',
  paneOpened: n => `Progress panel open: ${n} in progress.`,
  paneWaiting: 'The progress panel is waiting for room: widen the window or close another panel.',
  exitedWith: code => `exited with ${code}`,
  hiddenToast: 'Hidden · it comes back if the plan moves',
  chatOpenFailed: 'could not open the chat',
  resumeCopied: 'Copied: paste it into a terminal to go back to that chat',
  lessThanMin: 'under 1 min',
  justNow: 'just now',
  ago: span => `${span} ago`,
  tokens: n => tokens(n, '.', ''),
  activity: 'Activity',
  agents: n => count(n, 'agent', 'agents'),
  steps: n => count(n, 'step', 'steps'),
  stepLabel: i => `Step ${i}`,
  stepRef: i => `step ${i}`,
  stepOf: (i, total) => `step ${i} of ${total}`,
  stepsDone: (done, total) => `${done}/${total} steps`,
  unnamedDone: n => count(n, 'unnamed step', 'unnamed steps'),
  unnamedPending: n => count(n, 'unnamed pending step', 'unnamed pending steps'),
  acceptedAgent: 'accepted agent',
  stepClosed: 'step closed',
  agentsRunning: n => `${count(n, 'agent', 'agents')} running`,
  agentsHung: n => `${n} stuck?`,
  toReview: n => `${n} to review`,
  attentionHung: n => `${count(n, 'agent', 'agents')} running for over 1 h`,
  attentionReview: n => count(n, 'delivery to review', 'deliveries to review'),
  finished: 'finished',
  ringAlt: (done, total) => `${done} of ${total} steps`,
  stepsBefore: n => count(n, 'step before', 'steps before'),
  andMore: n => `and ${n} more`,
  fold: 'collapse',
  took: (steps, dur) => `${steps} in ${dur}`,
  left: n => `${n} left`,
  longestStepAnon: dur => `longest step: ${dur}`,
  longestAnon: dur => `longest: ${dur}`,
  longestNamed: (label, dur) => `longest: ${label} (${dur})`,
  stalled: (what, dur) => `${what}: no progress for ${dur}`,
  waitingForYou: 'waiting for your reply',
  nowInline: step => `now: ${step}`,
  nowHead: step => `Now: ${step}`,
  thenHead: steps => `Next: ${steps}`,
  thenInline: step => `next: ${step}`,
  panelButton: 'panel',
  planHead: name => `Plan: ${name}`,
  planSub: (total, first) => `${count(total, 'step', 'steps')}${first ? ` · starts with ${first}` : ''}`,
  openProgress: 'Open progress',
  showCommands: n => (n === 1 ? 'show the command' : `show the ${n} commands`),
  stalledState: dur => `Stalled · ${dur}`,
  paused: 'Paused',
  pausedFor: dur => `paused for ${dur}`,
  goToChat: 'Go to chat',
  hide: 'Hide',
  clear: 'Clear',
  close: 'Close',
  cancelledAt: (done, total) => `cancelled at ${done}/${total}`,
  loading: 'Reading cards…',
  noPlans: 'No plans.',
  secThisChat: 'IN THIS CHAT',
  secOthers: 'OTHER PLANS IN PROGRESS',
  secFinished: 'FINISHED TODAY IN OTHER CHATS',
  unreadable: name => `unreadable card: ${name}`,
  discreetMode: on => `Discreet mode: ${on ? 'on' : 'off'}`,
}

export const DICTS: Readonly<Record<Lang, Dict>> = { en, es }

export const dictFor = (lang: Lang): Dict => DICTS[lang]
