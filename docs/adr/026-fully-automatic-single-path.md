# ADR-026 — Un solo recorrido, completamente automático

Estado: aceptado e implementado en la Fase 13. Sustituye a ADR-023 (automatización por política) y
deja sin efecto, para el producto, las reglas de supervisión humana de ADR-013, ADR-015, ADR-016,
ADR-017, ADR-018, ADR-020, ADR-021 y ADR-022. Sus decisiones técnicas (revisiones inmutables,
`effect_sha256`, aritmética exacta, evidencia por cifra) siguen vigentes.

## Contexto

Las Fases 4 a 10 construyeron un recorrido **supervisado**: la persona confirmaba la semántica,
definía reglas y métricas, aprobaba el efecto exacto de cada limpieza, lanzaba planes, pulsaba
«Actualizar» en dashboards e informes y usaba el copiloto con botones. La Fase 11 añadió un
pipeline **gobernado por política** (11A–11E) que sólo arrancaba si una persona creaba y activaba
una política y se detenía hasta que confirmara un mapeo de molde. En paralelo, A1/B1/B2/C1/C2
crearon un recorrido **descriptivo sin configuración**: subir → perfil → dashboard → explicación.

El producto cambia de enfoque: no se quiere ninguna interacción manual. Tener dos automatizaciones
(una que exige configuración humana y otra que no) y además el recorrido manual es contradictorio
y difícil de mantener.

## Decisión

1. **Un solo recorrido**: el automático sin configuración (subir → leer → perfil → calidad →
   interpretación → dashboard → explicación IA opcional). Es la única experiencia del producto.
2. **Se retira el pipeline por política** (módulos `automation`, `analysis_sessions`, `templates`;
   API, interfaz y pruebas). La migración **0019** elimina sus tablas y sus datos (0013–0017). Es la
   única migración no aditiva del proyecto y se decidió explícitamente; su downgrade recrea las
   tablas vacías. La detección pura de contextos (ventas, inventario) pasa a
   `understanding/templates.py` sin cambiar el resultado de `understanding.profile@3`.
3. **Se retiran las funciones manuales de la API y de la interfaz**: revisión semántica, planes y
   catálogo, vista previa/aprobación/aplicación de limpieza, reglas de calidad, métricas, análisis
   a petición, dashboards editables, informes y PDF, chat del copiloto y auditoría textual con
   botón, y el demo guionizado de ventas. La API pasa a **0.18.0**.
4. **Se conservan los motores y servicios** que el recorrido automático usará en la Fase 14:
   planning (planes como sustrato de ejecución y validación), cleaning (vista previa, efecto y
   derivadas con linaje), quality (reglas `csv-quality-v2`), analytics (`analytics.query@1..3`,
   métricas y evidencia) y understanding (revisiones semánticas). Sus pruebas los siguen
   ejercitando mediante un router **sólo de pruebas** (`apps/api/tests/service_routes.py`) que
   reproduce la forma de las antiguas peticiones; nunca forma parte de la API ni de OpenAPI.
5. **Se eliminan los servicios sin consumidor**: dashboards editables (Fase 8), informes y PDF
   (Fase 9) y el chat del copiloto (Fase 10). Sólo quedan sus clases de tabla, porque **sus tablas y
   datos se conservan** (decisión de la Fase 13) y las pruebas de migraciones siguen comprobando sus
   garantías (inmutabilidad, restricciones). El copiloto queda reducido a la explicación automática
   (C2): disponibilidad, presupuesto y verificación de cifras.
6. **Principio del producto** (sustituye al «principio híbrido»): el motor determinista decide y
   calcula con reglas versionadas; la IA sólo explica resultados publicados; ninguna cifra sale del
   modelo; originales y versiones inmutables con linaje. _Modificado en la Fase 16 por
   [ADR-033](033-bounded-investigation-and-ai-proposals.md): la IA también propone investigaciones
   en un esquema cerrado, que Python valida y el motor calcula._

## Consecuencias

- Una carga produce resultados sin ninguna decisión humana; no hay bandeja de «revisión
  necesaria».
- Se pierden las políticas, mapeos, ejecuciones del pipeline y sesiones de análisis guardadas. Los
  dashboards que ese pipeline publicó siguen en sus tablas, sin interfaz.
- Las tablas de las Fases 4–10 quedan sin interfaz hasta que la Fase 14 decida reutilizarlas
  (p. ej. registrar como revisiones las decisiones automáticas) o retirarlas.
- `cleaning_approvals.approved_by` sigue exigiendo un usuario: la Fase 14 registrará la decisión
  automática con el propietario que subió el archivo y una tabla nueva que indica que decidió el
  sistema y con qué versión de reglas (decisión tomada al planificar la Fase 13).
- La dependencia `reportlab` queda sin uso en el código; se mantiene en `pyproject.toml` hasta que
  la Fase 14 decida si genera informes PDF automáticos.
- Las tablas `report_renders` y los tipos de ejecución `report_render` y artefacto `report_pdf`
  permanecen en los literales de `executions` para leer filas históricas.

## Alternativas descartadas

- Mantener el recorrido manual como «modo experto»: contradice el enfoque y duplica superficie.
- Conservar las tablas del pipeline por política sin uso: deja datos huérfanos de un diseño
  retirado.
- Borrar también las tablas de las Fases 4–10: pierde historia que la Fase 14 puede reutilizar.
