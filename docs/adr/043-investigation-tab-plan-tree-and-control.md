# ADR-043 — Pestaña Investigación: plan, árbol, evidencias, clasificación y control

Estado: aceptado e implementado en la Fase 25 (API 0.33.0, migración 0026; el catálogo de carga
sigue en `analysis-v13`). Documentación: [Fase 25](../architecture/phase-25.md). Modifica
[ADR-037](037-guided-exploration.md) (la exploración guiada pasa a ser la investigación) y
convive con [ADR-033](033-bounded-investigation-and-ai-proposals.md).

## Contexto

La especificación de la pestaña Investigación pide un motor que formule preguntas, ejecute
análisis, evalúe resultados y profundice cuando encuentre algo interesante, con:

- un plan en el que cada investigación tenga pregunta, motivo, columnas, método, resultado
  esperado, prioridad y dependencias;
- investigaciones secundarias en árbol, con límites de profundidad, cantidad, tiempo y coste;
- una evidencia por resultado (pregunta, hipótesis, columnas, filtros, operación, registros
  considerados, resultado, método, limitaciones y ejecución);
- una clasificación en cinco niveles;
- que el usuario pueda iniciar, pausar, cancelar, reanudar y consultar investigaciones
  anteriores y sus errores.

Había dos motores parciales: la investigación de la Fase 16 (seguimientos temporales de los
hallazgos, entrada del informe) y la exploración guiada de la Fase 20 (consultas `explore-v1` a
partir de la comprensión, que leen el dashboard y el informe). Ninguno tenía plan, árbol,
clasificación ni control.

## Decisión

1. **La exploración guiada se convierte en la investigación** (`investigation-v2`, operación
   `exploration.explore@2`). Ocupa el mismo lugar en la cola (tras la comprensión y antes del
   dashboard) y escribe el mismo artefacto `exploration`, al que añade `nodes`, `stopped`,
   `resumed_from`, `trigger` y `consumption`. Los `results` y `proposals` se siguen escribiendo
   como proyección, así que el dashboard y el informe lo leen igual. `exploration.explore@1`
   sigue registrado para los planes guardados.
2. **Catálogo cerrado `explore-v2`**: los tipos de `explore-v1` más `evolution` (serie mensual),
   `period_change` (últimos meses frente a los anteriores, con los periodos y los importes en la
   evidencia) y `outliers` (regla de Tukey). Los temporales sólo se ofrecen y se aceptan si la
   comprensión encontró un periodo: sin fechas no se inventan análisis temporales.
3. **Plan por reglas y por la IA** (prompt de propuesta v2): la evolución de la medida principal,
   la comparación de periodos (que depende de ella), el ranking de las dimensiones agrupables,
   las relaciones confirmadas y los valores atípicos. Lo que no supera la validación queda en el
   plan como «Hipótesis descartada» con su motivo.
4. **Árbol**: tras cada nivel, un resultado relevante o secundario abre preguntas secundarias
   (reglas como «¿el grupo que lidera también destaca en otra medida?», «¿cómo evolucionó?»,
   «¿qué grupo explica el cambio?», y las que proponga la IA, validadas igual). Límites por
   defecto: profundidad 2, 20 investigaciones, 3 hijos por resultado, 60 s, 2 llamadas a la IA y
   0,05 USD.
5. **Clasificación de reglas (`relevance-v1`)** con las cifras del motor: magnitud del efecto
   (peso del grupo principal frente a un reparto parejo, diferencia entre grupos, Spearman,
   cambio de la serie o entre ventanas, proporción de atípicos), calidad (registros
   considerados; con menos de la mitad se rebaja), consistencia (menos de 30 registros rebaja) y
   evidencia (método). **La IA interpreta y sólo puede rebajar** un resultado (prompt de juicio
   v2); nunca aporta cifras.
6. **Control** (migración 0026, tabla nueva `investigation_controls`, inmutable y sólo de
   añadir): pausar o cancelar registran una petición que el trabajo mira antes de cada
   investigación; se detiene conservando lo calculado y publica resultados parciales
   identificados (`stopped`). Reanudar (sólo pausada o detenida por tiempo, con pendientes) y
   volver a investigar crean otra ejecución; lo calculado no se repite y cada nodo conserva la
   ejecución que lo produjo. El historial lista todas las ejecuciones.
7. **Errores**: un fallo al calcular una investigación queda en su nodo («Error de ejecución»)
   y el resto sigue.

## Decisiones tomadas sin consulta

- **La investigación de la Fase 16 no se retira todavía.** Es la entrada del informe automático
  (su explicación de hallazgos con cifras verificadas) y cambiar esa entrada es trabajo de la
  fase del Informe. Se muestra en Análisis como «Seguimiento de los hallazgos» y la etapa de
  progreso se llama igual; la etapa de la exploración pasa a llamarse «Investigación».
- «Iniciar una investigación» es volver a investigar la versión con el mismo recorrido
  automático, sin formularios.
- Se pausa entre investigaciones, no a mitad de un cálculo.
- Una pregunta secundaria de reglas repetida o que no aplica no se muestra; una propuesta
  inválida de la IA sí (como hipótesis descartada).
- El «no relevante» de la IA rebaja la clase de reglas en vez de ocultar el resultado.

## Consecuencias

- El dashboard puede recibir más resultados (relevantes y secundarios). La simulación de la IA
  respeta el máximo de 12 elementos por sección.
- La evolución mensual admite gráfico de línea en el dashboard.
- El informe titula la sección «Investigación» en las cargas nuevas e indica la pregunta, los
  registros considerados y los excluidos de cada resultado.
