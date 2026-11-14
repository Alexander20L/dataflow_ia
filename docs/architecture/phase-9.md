# Fase 9 — Informes y exportaciones

API 0.13. [ADR-021](../adr/021-reports-and-exports.md).

Objetivo: generar un informe de un dataset propio y exportarlo conservando la trazabilidad de cada cifra.

## Recorrido

Análisis → «Calcular» → etapa **Explicación** → «Nuevo informe» → bloques (texto, resultado de análisis, tarjeta de dashboard, conclusión, limitaciones) → «Guardar revisión» → cada bloque de datos muestra su procedencia → «Exportar PDF (revisión N)» → el worker genera el PDF → «Descargar PDF». En cualquier versión, «Exportar vN» descarga su tabla en CSV; en cualquier resultado, «Exportar resultado».

## Informes

Revisiones inmutables como los demás editores (`expected_revision`, `Idempotency-Key`, sin cambios no hay revisión; 409 `REPORT_CONFLICT`). Un informe es de una versión de dataset (la que se ve al crearlo).

| Bloque           | Contenido                                                               |
| ---------------- | ----------------------------------------------------------------------- |
| `text`           | texto del usuario                                                       |
| `analysis`       | revisión de un plan de `analytics.query@1` o `@2` y su ejecución exacta |
| `dashboard_card` | revisión exacta de un dashboard y una de sus tarjetas                   |
| `conclusion`     | conclusión del usuario                                                  |
| `limitations`    | nota de limitaciones                                                    |

Cada bloque de datos muestra automáticamente su **procedencia**: dataset, versión, ejecución, plan, filtros, periodo y fecha de cálculo; las cifras conservan su `evidence_id` (tabla con «De dónde sale este número»). Los estados de error son los de los dashboards (ejecución fallida, datos insuficientes, requisito semántico pendiente, análisis no válido, sin calcular); un bloque con error no impide el resto ni el PDF.

**El informe nunca se recalcula solo.** «Actualizar bloques» es explícito: los análisis se vuelven a ejecutar sobre la versión elegida (se reutiliza el plan si la tabla y la revisión semántica coinciden; si no, plan nuevo con los mismos pasos) y las tarjetas pasan a la revisión vigente de su dashboard. Se crea una revisión nueva (`cause: refresh`) y la anterior se conserva; el historial permite ver y exportar cualquier revisión.

La demostración de `features/reports/report.tsx` sigue sólo para el fixture, etiquetada como demostración.

## Exportación CSV

`GET /versions/{id}/export.csv` (cualquier versión, también derivada; `/original` sigue devolviendo 409 en derivadas porque no tienen original) y `GET /executions/{id}/analysis.csv`. Parámetro `profile`:

|                                 | `standard` (no cambia nunca)                   | `excel_regional`                                 |
| ------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| Codificación                    | UTF-8 sin BOM                                  | UTF-8 con BOM (Excel lo usa para detectar UTF-8) |
| Separador / fin de línea        | `,` / LF                                       | `;` / CRLF                                       |
| Comillas                        | `"` sólo si hace falta (RFC 4180; `""` dentro) | igual                                            |
| Nulos                           | campo vacío (la ingesta lee vacío como nulo)   | igual                                            |
| Decimales                       | punto (celda canónica de la Fase 6)            | coma decimal en columnas decimales               |
| Fechas / booleanos              | ISO 8601 / `true` `false`                      | igual                                            |
| Cabecera                        | nombres de columna                             | igual                                            |
| Texto que empieza por `= + - @` | sin cambios                                    | prefijo `'` (Excel no lo ejecuta como fórmula)   |

Una fila nula de una sola columna se escribe como `""` (la ingesta salta las líneas en blanco). El CSV de un resultado añade una columna `… · evidence_id` junto a cada cifra (valor, base, variación, variación %, % del total y posición); el grupo sin valor queda vacío.

**Ida y vuelta**: exportar una versión de texto en el perfil estándar y volver a importarla da las mismas columnas y celdas. El hash lógico incluye los IDs de columna, propios de cada versión, así que la prueba lo recalcula sobre la tabla reimportada con los descriptores de la original y obtiene el mismo hash. Una versión tipada se exporta con sus celdas canónicas y vuelve como texto.

## PDF

`POST /report-revisions/{id}/pdf` encola una ejecución **`report_render`** del worker a partir de una revisión exacta:

- Entrada `report`: bootstrap prepara una instantánea (bloques, procedencia y resultados) antes de cerrar la transacción de metadatos y verifica el hash de la revisión.
- Operación interna `reports.render_pdf@1` (fuera del catálogo de usuario: `analysis-v6` no cambia), en un subproceso aislado sin base de datos, con **ReportLab**.
- Artefacto `report_pdf` con su SHA-256; `GET /report-pdfs/{execution_id}` lo descarga (cabecera `X-Content-SHA256`) y `GET /reports/{id}/pdfs` lista los generados. La tabla `report_renders` vincula cada ejecución con la revisión exacta. Nada de `window.print()`.

Contenido: título, dataset, versión, revisión del informe (número, ID y hash) y fecha de generación (también en el pie de cada página). Cada bloque de datos lleva al pie su procedencia y una tabla con las cifras exactas y su `evidence_id` (hasta 200 por bloque; el CSV las incluye todas). KPI como cifra destacada; barras y líneas como gráfico vectorial de ReportLab con las mismas filas (eje desde 0; un nulo no se dibuja), siempre seguido de su tabla. Un bloque con error muestra su estado.

## API 0.13

Informes: `GET/POST /projects/{id}/reports`, `GET /reports/{id}` (`?revision=` para una revisión anterior), `GET/POST /reports/{id}/revisions`, `POST /reports/{id}/refresh`, `GET /report-revisions/{id}`, `POST /report-revisions/{id}/pdf`, `GET /reports/{id}/pdfs`, `GET /report-pdfs/{execution_id}`. Exportación: `GET /versions/{id}/export.csv`, `GET /executions/{id}/analysis.csv`. Sesión y propietario en todas (ajeno: 404); Origin y CSRF en las mutaciones. En lo existente sólo se amplían dos enumeraciones: tipo de ejecución `report_render` y tipo de artefacto `report_pdf`.

## Arquitectura y persistencia

Módulo `reports`: sólo usa sus puertos, `audit`, los contratos de dashboards y la interfaz pública de executions y datasets (para el paso del worker); su cálculo (`pdf`, `processor`, `contracts`, `domain`) no accede a la base de datos (prueba AST). executions sigue sin conocer reports: un tipo de entrada `report` lo resuelve bootstrap y un registro del worker añade la operación interna.

Migración **0011**, sólo aditiva: `report_families`, `report_revisions`, `report_save_requests` y `report_renders` (las tres últimas inmutables por trigger). Downgrade bloqueado si hay informes. Dependencia nueva: `reportlab` 5.1 (con `pillow` y `charset-normalizer`), Python puro, igual en Windows y en `python:3.12-slim`. **Actualizar desde 0.12 / esquema 0010**: desplegar API y worker juntos (un worker 0.12 no atiende `report_render`).

## Pruebas

- CSV (`test_csv_export.py`): reglas de ambos perfiles, fila nula de una columna, ida y vuelta con un CSV difícil (comas, comillas, saltos de línea, espacios, `""`, Ñ, €), derivada tipada en ambos perfiles y resultado con `evidence_id` por cifra.
- Informes (`test_reports.py`): revisiones, procedencia, conflicto, idempotencia, historial, validación de bloques, PDF en el worker (idempotente, hash, descarga y procedencia leída del propio PDF) con un bloque cuya ejecución falló, «Actualizar bloques» sobre otra versión y la revisión vigente del dashboard, aislamiento y CSRF.
- Migración 0011; las pruebas de 0005–0010 excluyen sus tablas nuevas.
- Navegador (`reports.spec.ts`): CSV de la v2 derivada en ambos perfiles, informe con un análisis y sus textos, procedencia, PDF generado y descargado.

### Verificación local — 2026-11-06

Python 3.12.10. Backend: 370 pruebas (Ruff y mypy strict sin errores), contrato exportado sin diferencias y `contracts:check` correcto. Web: typecheck, lint, format y build correctos. E2E en serie: 19/19.
