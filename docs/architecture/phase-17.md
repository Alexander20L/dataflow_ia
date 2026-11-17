# Fase 17 — Consolidar la entrega

Estado: **implementada** (17A y 17B, API 0.24.0, sin migración; catálogo de carga `analysis-v12`).
Decisión: [ADR-034](../adr/034-automatic-report-and-stage-progress.md). Plan general en
[Fase 14](phase-14.md) (D4).

## Objetivo

Que cada carga termine en algo que se pueda entregar: un informe en PDF trazable, generado sin
intervención, y una interfaz que muestre primero lo importante y en qué etapa va el trabajo.

## Recorrido

```
carga ─▶ hallazgos ─▶ trabajo «investigation» ─▶ trabajo «automatic_report»
 (análisis del archivo)      (investigación)          (informe: delivery.report@1 ─▶ report_pdf)
```

Las tres etapas se leen en `GET /versions/{id}/progress`; los dos últimos trabajos son de fondo y
esperan a las cargas nuevas.

## Contenido del informe (`automatic-report-v1`)

1. **Resumen**: archivo, versión, filas y los cinco hallazgos más importantes con sus cifras.
2. **Explicación automática (IA)**: resumen, alertas y recomendaciones ya verificadas; cada cifra
   lleva su evidencia entre corchetes y las retiradas aparecen como «[cifra retirada]». Sin IA se
   indica el motivo.
3. **Hallazgos**: todos, en el orden del plan, con cobertura, notas, tabla de cifras y gráfico.
4. **Investigación**: cada seguimiento con su origen (regla o IA) y motivo; propuestas
   rechazadas con su motivo; por qué se detuvo y consumo de IA.
5. **Calidad de los datos** y **revisión analítica** (con los análisis afectados).
6. **Análisis omitidos** y **limitaciones**.
7. **Anexo: evidencias**: cada `evidence_id` citado con su cifra, valor y método.

El informe no calcula ni llama a la IA: reordena lo publicado. Las cifras se muestran con formato
español sin redondear.

## API

| Ruta                            | Respuesta                                                      |
| ------------------------------- | -------------------------------------------------------------- |
| `GET /versions/{id}/progress`   | Etapas `analysis`, `investigation`, `report` y `complete`      |
| `GET /versions/{id}/report`     | `queued`, `running`, `ready` (nombre, tamaño, hash) o `failed` |
| `GET /versions/{id}/report.pdf` | PDF; 409 `REPORT_NOT_READY` mientras no esté listo             |

Versiones procesadas antes de esta fase: 404 `REPORT_NOT_AVAILABLE` y la etapa «Informe» como
«No aplica».

## Interfaz

«Resumen» arriba: etapas con su estado, tres hallazgos principales y «Descargar informe (PDF)»
cuando está listo. Debajo: hallazgos, investigación y dashboard. Se consulta el progreso cada
1,5 s mientras quede alguna etapa pendiente.

## Decisiones tomadas en la fase

- Módulo nuevo `delivery` en lugar de reabrir `reports` (la Fase 13 lo dejó sólo con sus tablas
  y una prueba AST lo protege).
- Un solo artefacto (`report_pdf`, tipo existente); el documento intermedio no se guarda porque
  se reconstruye de forma determinista a partir de lo publicado.
- PDF en el proceso del worker (contenido acotado, sin filas), con `invariant=1`.
- Tablas sin uso de las Fases 4–10: se conservan como archivo histórico (decisión del usuario).

## Pruebas

`tests/test_phase17_delivery.py`: cifras copiadas tal cual y evidencias conocidas, ausencia de IA,
PDF reproducible, formato sin redondeo, progreso por etapas y recorrido completo hasta la
descarga (otra cuenta: 404). `test_architecture.py`: `delivery` sólo lee contratos publicados y
ReportLab sólo en `pdf.py`. E2E: el resumen muestra las tres etapas y el PDF se descarga.
