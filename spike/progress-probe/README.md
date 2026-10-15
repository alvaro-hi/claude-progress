# progress-probe — prueba F0 de la 1.2.0

Mod temporal que solo apunta, un JSON por evento, si los hooks de un mod ven las herramientas que inyecta la app de escritorio (`mcp__ccd_turn__update_plan` y `mcp__ccd_turn__wrap_up`). Se instaló a nivel de usuario el 2026-10-15, corrió en una sesión de prueba de la app (tarea de 4 pasos) y se desinstaló.

## Resultado

| Evento del mod | ¿Ve `update_plan` y `wrap_up`? | Qué trae |
|---|---|---|
| `classic.PostToolUse` | Sí, en todas las llamadas | `tool_input` completo, `tool_response` (texto «Plan updated: step 2 of 4 is in progress.»), `session_id`, `prompt_id`, `transcript_path`, `cwd` |
| `classic.PreToolUse` | Sí | El envoltorio de la llamada |
| `tool.call` | Sí, antes y después | La entrada y el resultado |
| `prompt.compose` | Sí, en `tools` | `surfaces` llega vacío: la detección va por `tools`, no por superficie |
| `$.tool.list()` en `session.start` | Sí | Las dos herramientas, entre las demás `mcp__ccd_*` |
| `ui.render` de `ToolUse` | No llegó ninguna fila de estas herramientas | La app dibuja su propia tarjeta |

Secuencia vista en la sesión de prueba: `items` (4 pasos, `scope: first_task`) → `advance` ×3 → `wrap_up`. El último paso no recibe su propio `advance`: lo cierra `wrap_up`.

`f0-log/` guarda los 25 eventos de esa sesión, con las rutas personales cambiadas. Sirven de datos de ejemplo para los tests de F1.

Esta carpeta se borra antes de fusionar `native-plan` en `main`.
