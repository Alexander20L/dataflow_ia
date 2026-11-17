# ADR-029 — Explicación automática con IA del dashboard publicado

Estado: aceptado e implementado en el incremento C2 (API 0.17); registrado retroactivamente. Activación
por defecto modificada por [ADR-027](027-excel-and-ai-without-configuration.md) (Fase 13B).
Documentación: [analista automático, C2](../architecture/automatic-analyst.md#c2--explicación-automática-sobre-el-dashboard-publicado-api-017).
Sustituye, para el producto, al copiloto conversacional de [ADR-022](022-ai-copilot.md), retirado en la
Fase 13 ([ADR-026](026-fully-automatic-single-path.md)).

## Contexto

El dashboard descriptivo (B1, C1) se publica sin intervención, pero sólo con cifras y reglas. Se quería
una explicación en lenguaje natural sin botones ni conversaciones y sin que el modelo pueda inventar
cifras, ver filas ni cambiar resultados.

## Decisión

1. **Trabajo propio tras publicar**: la publicación de una importación con `understanding.profile@2/@3`
   encola `overview_audit` (operación interna `copilot.audit_overview@1`, fuera del catálogo) si hay
   proveedor efectivo. Fija ID y SHA-256 del perfil, la versión y la ejecución productora. Reutiliza
   la cola, autorizaciones y fencing de `executions`; no crea versiones ni altera datos o dashboards.
2. **La IA sólo explica**: el prompt `automatic-overview-audit@1` recibe como máximo 64 cifras
   agregadas (KPI y puntos de gráficos), sus etiquetas marcadas como no confiables y las
   limitaciones; el contexto se limita a 64 KB. Nunca recibe `table_detail`, ejemplos, filas ni
   archivos. Cambiar el prompt exige subir su versión.
3. **Ninguna cifra sale del modelo**: la salida (resumen, hasta tres alertas, dos recomendaciones)
   sólo cita cifras como `{{evidence:id}}`; el verificador las sustituye por los valores exactos,
   retira números libres y rechaza referencias desconocidas. La verificación cubre cifras, no la
   corrección semántica de toda la prosa.
4. **Presupuesto y disponibilidad**: tokens diarios por usuario (`DATAFLOW_AI_USER_DAILY_TOKENS`,
   200 000) y coste mensual por proyecto (`DATAFLOW_AI_PROJECT_MONTHLY_COST_USD`, 5 USD) sobre el
   consumo registrado; límite de salida `DATAFLOW_AI_MAX_OUTPUT_TOKENS` (4 000).
5. **Un solo intento**: sin reintentos del trabajo ni del SDK; timeout por debajo del plazo de
   procesamiento. Un fallo del proveedor, una salida inválida o el presupuesto agotado dejan el
   trabajo fallido y el dashboard intacto.
6. **Sólo lectura en la interfaz**: los GET de estado y evidencia nunca llaman al proveedor; la
   interfaz consulta y hace polling sólo mientras el trabajo está pendiente. Sin botones.
7. El SDK de Anthropic sólo se importa en `integrations/ai/anthropic_provider.py`; pytest y E2E usan
   el proveedor `fake` o `disabled`.

## Consecuencias

- Toda carga nueva con IA disponible obtiene una explicación verificada sin acciones de la persona.
- Los controles de presupuesto **no son reservas durables**: con trabajos concurrentes el techo
  puede superarse, y una caída tras la llamada puede dejar consumo sin registrar. Endurecerlo queda
  pendiente.
- Sin generación retroactiva para versiones anteriores a C2.

## Alternativas descartadas

- Mantener el chat del copiloto o un botón «Explicar»: exige intervención y contradice ADR-026.
- Enviar filas o muestras al modelo: expone datos y no es necesario para explicar agregados.
- Reintentar automáticamente: puede facturar varias llamadas por un mismo resultado.
