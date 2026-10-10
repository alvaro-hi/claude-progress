// Contrato del mod: la foto de ~/.claude/progress que pintan la banda y el panel.

export type Child = {
  label: string
  state: string
  started: string
}

/** Una fila de la lista de pasos: cerrados en el orden en que se cerraron, luego pendientes del plan. */
export type StepRow = {
  /** clave del paso (historial o plan); vacía en las filas agrupadas */
  key: string
  label: string
  at: string
  /** tokens gastados en el paso (sesión y agentes); ausente si no se midió */
  tok?: number
  isDone: boolean
  /** false en las filas que agrupan pasos sin nombre: esas no se esconden en modo discreto */
  isNamed: boolean
}

export type Ficha = {
  id: string
  title: string
  cwd: string
  done: number
  total: number
  iter: [number, number] | null
  step: string
  status: string
  started: string
  updated: string
  owner: string | null
  children: Child[]
  steps: StepRow[]
  /** tokens gastados en el plan (sesión y agentes); ausente si no se midió */
  tokens?: number
  /** el usuario la ha ocultado: fuera de la lista hasta que el plan se mueva */
  hidden: boolean
  /** el último chat que la tocó: en la app de escritorio, su id de la app; si no, el de la sesión */
  chat?: { app: 'desktop' | 'cli'; id: string }
}

export type Snap = {
  fichas: Ficha[]
  bad: string[]
  discreet: boolean
  sessionId: string
  cwd: string
  now: number
  /** sesiones con un turno en marcha (de ~/.claude/progress/_turns, que escriben los hooks) */
  working: string[]
}

declare module 'claude-code' {
  interface PluginState {
    progress: {
      snap: Snap | null
      /** fichas desplegadas en el panel */
      open: string[]
      /** fichas con todos los pasos visibles (ventana abierta) */
      full: string[]
      /** banda fijada abierta */
      pinned: boolean
      /** grupos de comandos desplegados por un hito */
      groups: string[]
      closing: string | null
      /** locale del entorno (LC_ALL, LC_MESSAGES, LANG) para el idioma `auto`; null hasta leerlo */
      locale: string | null
    }
  }
}
