// Sonda temporal (prueba F0 de la 1.2.0): ¿ven los hooks de un mod las herramientas que inyecta la app
// de escritorio (mcp__ccd_turn__update_plan, mcp__ccd_turn__wrap_up)? Solo escribe un JSON por evento en
// ~/.claude/progress-probe/ y deja pasar todo tal cual. Un Bash de control prueba que la sonda está viva.
import type { EngineInterface, Register } from 'claude-code'

const CCD = 'mcp__ccd_turn__'
let seq = 0
const seen = new Set<string>()

async function log($: EngineInterface, event: string, data: unknown): Promise<void> {
  try {
    const home = (await $.env.get('HOME')) ?? ''
    const sid = (await $.session.id()).slice(0, 8)
    const now = await $.clock.now()
    seq += 1
    const name = `${now}-${sid}-${String(seq).padStart(3, '0')}-${event.replace(/[^A-Za-z0-9]+/g, '_')}.json`
    await $.fs.write(`${home}/.claude/progress-probe/${name}`, JSON.stringify({ event, at: now, data }, null, 2))
  } catch {
    // una sonda nunca rompe la sesión
  }
}

function once(key: string): boolean {
  if (seen.has(key)) return false
  seen.add(key)
  return true
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    const tools = (await $.tool.list()).map(t => t.name)
    await log($, 'session.start', {
      surfaces: await $.session.surfaces(),
      ccdTools: tools.filter(n => n.startsWith('mcp__ccd_')),
      toolCount: tools.length,
    })
    return r
  }).catch(($, e, next) => next(e))

  on('prompt.compose', async ($, e, next) => {
    if (once('compose')) {
      await log($, 'prompt.compose', { surfaces: e.surfaces, ccdTools: e.tools.filter(n => n.startsWith('mcp__ccd_')) })
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', async ($, e, next) => {
    const ccd = e.tool.startsWith(CCD)
    const control = e.tool === 'Bash' && once('control-tool.call')
    if (ccd || control) await log($, `tool.call-in-${e.tool}`, e)
    const r = await next(e)
    if (ccd) await log($, `tool.call-out-${e.tool}`, r)
    return r
  }).catch(($, e, next) => next(e))

  on('classic.PreToolUse', async ($, e, next) => {
    if (e.tool.startsWith(CCD) || (e.tool === 'Bash' && once('control-pre'))) await log($, `classic.PreToolUse-${e.tool}`, e)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('classic.PostToolUse', async ($, e, next) => {
    const r = await next(e)
    if (e.tool_name.startsWith(CCD) || (e.tool_name === 'Bash' && once('control-post'))) {
      await log($, `classic.PostToolUse-${e.tool_name}`, e)
    }
    return r
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const p = e.props
    if (p.tool.startsWith(CCD) && once(`${p.tool_use_id}-${p.isRunning}-${e.surface}`)) {
      await log($, `ui.render-ToolUse-${p.tool}`, { surface: e.surface, props: p })
    }
    return next(e)
  })
}
