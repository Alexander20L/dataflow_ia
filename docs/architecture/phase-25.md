# Fase 25 — Pestaña Investigación

Estado: **implementada** (API 0.33.0, migración 0026, catálogo de carga `analysis-v13`).
Decisión: [ADR-043](../adr/043-investigation-tab-plan-tree-and-control.md). Parte de la
[Fase 20](phase-20.md) (exploración guiada) y de la [Fase 24](phase-24.md) (comprensión).

## Objetivo

Que el sistema investigue como un analista: propone un plan, calcula cada pregunta sobre todas
las filas, evalúa el resultado, profundiza cuando encuentra algo interesante y deja cada
hallazgo con su evidencia. El usuario puede pausar, cancelar, reanudar, volver a investigar y
consultar las investigaciones anteriores.

## Recorrido

```
comprensión ─▶ exploration (exploration.explore@2, investigation-v2)
                 plan (reglas + IA) ─▶ por niveles: calcular ─▶ evaluar (relevance-v1)
                                     ─▶ juicio de la IA ─▶ profundizar o terminar
                 (antes de cada cálculo: pausa, cancelación y límites)
             ─▶ dashboard ─▶ informe
control del usuario ─▶ investigation_controls (pausa/cancelación)
                    └▶ otra ejecución exploration (reanudar / volver a investigar)
```

## Piezas

| Pieza                                          | Dónde                                                    |
| ---------------------------------------------- | -------------------------------------------------------- |
| Contratos (nodo, clase, control, historial)    | `modules/exploration/contracts.py`                       |
| Validación `explore-v2` y catálogo con periodo | `modules/exploration/domain.py`                          |
| Evolución, cambio de periodo y atípicos        | `modules/exploration/engine.py` (Polars)                 |
| Plan, árbol y clasificación `relevance-v1`     | `modules/exploration/plan.py` (puro)                     |
| Ciclo acotado con puertos                      | `modules/exploration/investigator.py`                    |
| Peticiones de control (0026)                   | `modules/exploration/infrastructure.py`, migración 0026  |
| Prompts de propuesta y juicio v2               | `modules/copilot/exploration.py`, `copilot/contracts.py` |
| Trabajo, reanudar, historial y control         | `bootstrap/exploration_job.py`                           |
| Línea para la evolución en el dashboard        | `modules/delivery/dashboard.py`                          |
| Sección «Investigación» del informe            | `modules/delivery/domain.py`                             |
| Pestaña Investigación                          | `apps/web/src/features/investigation/`                   |

## API

- `GET /api/v1/versions/{id}/exploration` añade `control` (petición pendiente) y `resumable`, y
  admite `execution_id` para ver una investigación anterior. El artefacto añade `nodes`,
  `stopped`, `resumed_from`, `trigger` y `consumption`.
- `GET /api/v1/versions/{id}/exploration/history` (`getInvestigationHistory`): las
  investigaciones de la versión.
- `POST /api/v1/versions/{id}/exploration/control` (`controlInvestigation`), con `action`
  `pause`, `cancel`, `resume` o `restart`. Responde 409 `INVESTIGATION_FINISHED`,
  `INVESTIGATION_RUNNING` o `INVESTIGATION_NOT_RESUMABLE` si la acción no corresponde al estado.

## Interfaz

La pestaña **Investigación** va entre Comprensión y Análisis:

- arriba, el estado (por qué se detuvo, consumo) y los botones Pausar y Cancelar o Reanudar y
  Volver a investigar;
- **Plan**: las investigaciones iniciales con pregunta, hipótesis, motivo, columnas, método,
  resultado esperado, prioridad, dependencias y estado;
- **Árbol**: las investigaciones secundarias con su clase y la decisión de profundizar o terminar;
- **Evidencias**: cada resultado con filtros, operación, registros considerados, cifras (cada una
  con su evidencia), método, evaluación, limitaciones y ejecución, filtrable por clase;
- **Historial**: las ejecuciones anteriores, que se pueden abrir.

El panel «Exploración guiada» sale de Análisis. La investigación de la Fase 16 sigue allí como
«Seguimiento de los hallazgos».

## Pruebas

- `tests/test_phase25_investigation.py` cubre los criterios de la especificación: plan
  pertinente y completo, sin análisis temporales si no hay fechas, sumas para medidas aditivas,
  hipótesis inválida descartada, árbol que profundiza, cálculo sobre todas las filas en orden
  cronológico, evidencia por nodo, clasificación por magnitud, calidad y tamaño, la IA que sólo
  rebaja, límites de tiempo e investigaciones con reanudación, errores de ejecución registrados,
  pausa y cancelación, y el control y el historial por la API.
- `test_migration_0026.py`: ida y vuelta, `compare_metadata`, primera petición vigente,
  inmutabilidad, acción válida y downgrade bloqueado con datos.
- E2E: `investigation.spec.ts` (plan, árbol, evidencias, volver a investigar e historial) y
  `analysis.spec.ts` (la propuesta inválida descartada en el plan).

## Limitaciones

- La investigación de la Fase 16 sigue como entrada del informe; su retirada corresponde a la
  fase del Informe.
- La pausa se atiende al terminar la investigación en curso.
- Las versiones exploradas antes de la fase no tienen plan ni árbol: muestran sus resultados y
  se pueden volver a investigar.
