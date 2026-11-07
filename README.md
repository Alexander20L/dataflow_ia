# DataFlow AI

**API 0.17 — dashboard, interpretación y explicación automáticos:** las nuevas cargas CSV y Excel generan indicadores, gráficos y detalle sin políticas ni confirmaciones. Si la IA está configurada, un trabajo independiente explica los resultados guardados con cifras verificadas y evidencia enlazada. Sin IA o ante errores, el dashboard sigue disponible. No se envían filas de detalle ni muestras del perfil al modelo; sólo cifras agregadas acotadas, sus etiquetas y limitaciones. Las herramientas avanzadas siguen siendo opcionales. [Plan y avance](docs/architecture/automatic-analyst.md).

Plataforma de análisis de datos supervisado. **API 0.14 / Fase 10:** copiloto de IA que traduce peticiones en lenguaje natural a consultas, métricas y limpiezas del catálogo, pregunta cuando falta una definición de negocio y explica los resultados con cifras verificadas por su evidencia; nada se ejecuta sin tu confirmación y la IA está desactivada por defecto. **Fase 9:** informes con procedencia por bloque, exportación a PDF generada en el servidor y CSV con perfil estándar o Excel regional. **Fase 8:** dashboards persistidos con tus propios análisis: tarjetas KPI, tabla, barras o líneas que muestran ejecuciones exactas, filtros globales y «Actualizar» explícito sobre la versión elegida. **Fase 7:** análisis de negocio determinista sobre CSV propios con métricas que define el usuario (columna, agregación, filtros y fecha de negocio), comparaciones con el periodo anterior o el mismo periodo del año anterior, top N y % del total, y evidencia rastreable por cifra. **Fase 6:** limpieza supervisada de CSV propios con conversiones de tipo (entero, decimal, fecha, booleano), marcadores de nulo, deduplicación, recorte de espacios y exclusión de registros: vista previa sobre todo el dataset, aprobación del efecto exacto y versión derivada con columnas tipadas y diagnóstico nuevo; el original no cambia. Si un valor no convierte, no se publica nada y se listan los valores y el motivo. Además, reglas de calidad configurables (obligatoriedad, clave única, rango, catálogo de valores, formato convertible) que se evalúan aparte de la completitud técnica. Incluye los planes versionados de Fase 4, el contexto semántico de Fase 3 y CSV, originales, perfilado y calidad reales. Exploración y etapas posteriores continúan como demostración independiente.

## Ejecutar

Requisitos: Node.js 24 LTS, npm 11, Python 3.12+ y Docker Desktop iniciado.

### Preparación (PowerShell, desde la raíz)

```powershell
npm install
docker compose -f infrastructure/compose/compose.yaml up -d postgres
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python.exe -m pip install -c apps/api/requirements.lock -e "apps/api[dev]"
```

### Terminal 1: API

Desde `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m dataflow.bootstrap.run --with-worker
```

Aplica Alembic, inicia un worker en otro proceso y escucha en http://127.0.0.1:8000. Swagger: http://127.0.0.1:8000/docs. Para ejecutar el worker por separado: `python -m dataflow.bootstrap.worker` desde el mismo entorno/carpeta de API y con la misma configuración.

### Terminal 2: frontend

Desde la raíz:

```powershell
npm run dev --workspace @dataflow/web -- --port 3002
```

Abrir http://localhost:3002 y crear una cuenta (contraseña de 12 caracteres como mínimo). No existen usuarios ni contraseñas predeterminados.

### Copiloto de IA (opcional)

Está desactivado por defecto y el producto funciona igual sin él. Para activarlo en local, en `apps/api/.env` (ignorado por git; nunca en el repositorio ni en el frontend):

```sh
DATAFLOW_AI_PROVIDER=anthropic
DATAFLOW_AI_API_KEY=<tu clave de la API de Anthropic>
# Opcional: DATAFLOW_AI_MODEL=claude-opus-5-5 · DATAFLOW_AI_EFFORT=low
```

Con Docker, guarda la clave en un archivo fuera del repositorio (o en `infrastructure/compose/secrets/`, que git ignora) y arranca con `DATAFLOW_AI_PROVIDER=anthropic` y `DATAFLOW_AI_API_KEY_SECRET_FILE=<ruta del archivo>`: se monta como secreto en `/run/secrets/ai_api_key`. Límites de uso por usuario y día (tokens) y por proyecto y mes (costo estimado) en `apps/api/.env.example`. `DATAFLOW_AI_PROVIDER=fake` usa un proveedor determinista sin red (pruebas y E2E). Casos reales opcionales contra el modelo: `DATAFLOW_AI_LIVE_TESTS=1` con la clave configurada y `pytest apps/api/tests/ai/test_ai_live.py` (generan costo).
Variables opcionales en `apps/api/.env` y `apps/web/.env.local`: consultar sus `.env.example`. El frontend usa un proxy same-origin, `API_INTERNAL_URL` privado y cookies HttpOnly. No requiere CORS abierto.

### Calidad y pruebas

```sh
npm run lint
npm run typecheck
npm run build
npm run format:check

# Desde la raíz; backend con PostgreSQL real, esquema efímero y rollback
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -q
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/src apps/api/tests apps/api/migrations apps/api/scripts

# Desde apps/api
.venv/Scripts/python.exe -m mypy

# Desde la raíz: navegador para pruebas E2E y base exclusiva
npx playwright install chromium
apps/api/.venv/Scripts/python.exe apps/api/scripts/prepare_e2e_db.py
npm run test:e2e
```

Playwright requiere una compilación previa (`npm run build`), inicia su propia API en 8001 y frontend en 3100. Las pruebas se ejecutan en serie (`workers: 1` en `playwright.config.ts`): comparten esa API y un único worker de cola, y en paralelo sólo competirían por él y agotarían sus esperas, también en CI. Usa `dataflow_e2e`, aplica migraciones y no vacía la base del usuario. Para CI o Python fuera de `.venv`: `DATAFLOW_PYTHON`; conexión específica: `DATAFLOW_E2E_DATABASE_URL` (nombre terminado en `_e2e`).

### Actualizar contrato

```powershell
apps/api/.venv/Scripts/python.exe apps/api/scripts/export_openapi.py
npm run api:generate
```

No editar `contracts/openapi/dataflow.json` ni `packages/api-client/src/schema.ts` manualmente. Exportar con Python 3.12 (como CI): desde 3.13 cambian frases HTTP y el contrato difiere.

## Recorrido

Crear cuenta → Nuevo análisis → seleccionar CSV → conservar original → procesamiento en cola → vista previa → entendimiento → calidad → registros afectados. También se pueden crear proyectos vacíos y subir el CSV después.

Prueba con `examples/ventas_calidad.csv`: 6 registros, 5 columnas, una celda vacía, una fila duplicada adicional y una celda de espacios. Completitud: 96,67 %. Usa un CSV propio para obtener sus cifras reales.

Los proyectos se guardan en PostgreSQL con propietario, revisión y eventos de auditoría. La búsqueda y paginación se realizan en el backend. Un usuario no puede listar, leer, editar ni archivar proyectos ajenos. Ediciones obsoletas devuelven 409.

El enlace **Explorar ventas 2026** abre el fixture: workspace → calidad → aprobar limpieza → ejecutar → explorar → informe.

El fixture contiene 240 ventas y 8 importes nulos. Su limpieza demostrativa crea una vista v2 de 232 registros y mantiene v1 intacta. No se atribuyen esos resultados a archivos propios. Los CSV reales tienen sus propias versiones y diagnósticos, y no se limpian automáticamente. Las conexiones externas están pendientes; el copiloto con IA real sólo trabaja sobre datos propios.

### CSV admitidos

- UTF-8 con o sin BOM; coma, punto y coma o tabulador, con detección automática u opción explícita.
- Hasta 5 MiB, 100.000 registros, 128 columnas y 10.000 caracteres por campo. Cabecera única y no vacía; errores estructurales se muestran sin publicar resultados parciales.
- Original byte a byte y SHA-256. Copia Parquet con texto nullable: conserva ceros iniciales y espacios; campos vacíos se representan como nulos. Los tipos sugeridos son heurísticos y no convierten los valores.
- Reglas: vacíos por columna, duplicados posteriores a su primera aparición y campos sólo con espacios/tabuladores/saltos. Completitud mide celdas no vacías; no una calidad universal.
- Cuota inicial de 100 MiB de originales por cuenta; una carga activa por proyecto y tres por cuenta. XLSX/Parquet y conectores se integrarán después.

Las cargas se confirman con metadatos y trabajo en una transacción PostgreSQL. El worker usa leases, fencing, máximo tres intentos y subproceso con timeout. Un intento antiguo o cancelado no publica artefactos. Puedes cerrar el navegador durante el procesamiento.

En cada CSV procesado, **Planes y ejecuciones** permite armar un plan con operaciones del catálogo (perfil, calidad), guardarlo como revisión inmutable sobre una tabla identificada por su hash y ejecutarlo. Un plan incompleto muestra qué le falta y no se ejecuta. Cambiar la versión predeterminada no altera la entrada de un plan. Cada ejecución conserva su plan, resultados e historial. El diagnóstico baseline permanece fijo; ejecutar análisis no crea otra versión del archivo. [Documentación Fase 4](docs/architecture/phase-4.md).

En la etapa **Limpieza** de un CSV propio, la propuesta se arma desde el diagnóstico (Q-003 → recortar espacios; Q-001 → excluir nulos). La vista previa calcula el efecto exacto sobre todo el dataset y destaca los nulos creados, porque limpiar puede bajar la completitud. Tras aprobar ese efecto, aplicarlo publica una versión derivada (v2) con su propio diagnóstico y linaje; v1 y su original se conservan y siguen seleccionables. La derivada no pasa a ser la predeterminada. [Documentación Fase 5](docs/architecture/phase-5.md).

Desde la Fase 6A la propuesta también convierte tipos con formatos exactos (sin recortar ni aceptar formatos regionales), convierte marcadores como «NA» en nulos y elimina duplicados conservando la primera aparición. Una columna confirmada como identificador en la revisión semántica exige confirmar su conversión a número, y un código con ceros a la izquierda («007») nunca se convierte. [Documentación Fase 6](docs/architecture/phase-6.md).

En **Análisis** se definen métricas (por ejemplo, «Ingresos» = suma de importe por fecha de negocio) y se consultan por dimensiones, granularidad temporal y periodo. Una suma o una media exigen que la columna esté confirmada como medida en Entendimiento, y la fecha como fecha de negocio; si falta, el análisis lo indica y enlaza con Entendimiento. Cada cifra abre «De dónde sale este número»: definición, filtros, versión de datos, revisión semántica y filas excluidas por filtros o por nulos. Los nulos nunca cuentan como cero. «Comparar y ordenar» añade la comparación con el periodo anterior o con el mismo periodo del año anterior (variación absoluta y porcentual; un periodo sin datos se muestra como tal, nunca como 0), un top N por una métrica (dos valores iguales se ordenan por las dimensiones y se marcan con «=») y el % del total de sumas y conteos, calculado sobre todos los grupos aunque el top N oculte algunos. Esas cifras también abren su procedencia. [Documentación Fase 7](docs/architecture/phase-7.md).

En **Visualización** se guardan dashboards: desde Análisis, «Añadir a un dashboard» crea una tarjeta (KPI, tabla, barras o líneas) que apunta a ese análisis y a su ejecución exacta. Las tarjetas se ordenan con botones y tienen tamaño pequeño, mediano o grande; los filtros globales sólo ocultan filas en las tarjetas que agrupan por esa dimensión (en las demás dicen «Filtro no aplicable»). Cada tarjeta muestra la versión y la fecha de su ejecución, y sus cifras abren «De dónde sale este número». El dashboard no cambia solo al subir datos: «Actualizar» vuelve a calcular las tarjetas sobre la versión elegida y guarda una revisión nueva; si una no se puede calcular (por ejemplo, falta confirmar la semántica), lo indica sin afectar a las demás. [Documentación Fase 8](docs/architecture/phase-8.md).

En **Explicación** se escriben informes: bloques de texto, resultados de análisis, tarjetas de dashboard, conclusión y limitaciones. Cada bloque de datos muestra de dónde sale (dataset, versión, ejecución, filtros y fecha) y sus cifras abren su evidencia; el informe no se recalcula solo («Actualizar bloques» guarda una revisión nueva). «Exportar PDF» lo genera en el servidor a partir de la revisión exacta, con la procedencia al pie de cada bloque. «Exportar vN» descarga la tabla de cualquier versión (también derivada) en CSV estándar (coma, punto decimal; se vuelve a importar sin cambios) o Excel regional (punto y coma y coma decimal), y «Exportar resultado» hace lo mismo con un análisis, con el `evidence_id` de cada cifra. [Documentación Fase 9](docs/architecture/phase-9.md).

El panel **Copiloto de análisis** (debajo de cada etapa de un CSV propio) recibe peticiones como «Compara las ventas mensuales por región». Si falta una definición de negocio (métrica, medida o fecha de negocio confirmada, moneda) pregunta y enlaza a donde se resuelve; si no, propone una consulta, una métrica o un plan de limpieza como tarjeta con su validación y botones explícitos («Ejecutar consulta», «Crear métrica», «Abrir plan de limpieza»). Las limpiezas siguen la vista previa y la aprobación de siempre. «Explicar resultado» redacta una explicación cuyas cifras salen de la evidencia del resultado y abren «De dónde sale este número»; un número que el modelo escriba por su cuenta se retira y se marca. Al proveedor sólo se envían nombres, tipos y roles de columnas, métricas, conteos agregados y, al explicar, el resultado calculado; nunca filas ni valores de ejemplo. [Documentación Fase 10](docs/architecture/phase-10.md).

En **Calidad → Reglas de calidad del proyecto** se definen reglas de negocio por columna (csv-quality-v2), se guardan como revisiones inmutables y se evalúan como un plan: el informe separa la calidad técnica (Q-001 a Q-003, completitud) de las reglas del usuario. Las reglas sirven para la tabla y sus versiones derivadas.

En **Entendimiento → Revisión semántica** declara filas, roles, interpretación, claves, unidades/moneda y nulos. Guarda revisiones parciales y consulta su historial. No convierte ni limpia valores. Un plan puede fijar una revisión exacta o continuar sin contrato para análisis técnicos. [Documentación Fase 3](docs/architecture/phase-3.md).

Sólo el tema y la limpieza del ejemplo se conservan en localStorage (`dataflow-ui-v2`). Restablecer la demo no elimina proyectos de la cuenta. El almacenamiento legado `dataflow-demo-v1` se conserva sin importar sus proyectos automáticamente: no se atribuyen datos locales a una cuenta sin una migración explícita.

## Estructura

- `apps/web`: aplicación Next.js independiente, funcionalidades en `src/features`.
- `apps/api`: monolito modular FastAPI; casos de uso con puertos, repositorios SQL y routers separados. `src/dataflow/integrations/ai`: puerto del proveedor de IA (único lugar que importa su SDK).
- `packages/api-client`: cliente tipado desde OpenAPI, sin tipos HTTP duplicados a mano.
- `contracts/openapi`: instantánea versionada del contrato.
- `infrastructure/compose`: PostgreSQL y despliegue local completo.
- `docs/architecture`: arquitectura, contratos y hoja de ruta.
- `docs/adr`: decisiones arquitectónicas.

El worker reutiliza el monolito modular, sin duplicar reglas. El frontend y la API son desplegables independientemente. El adaptador local de objetos es de desarrollo; S3 y retención/eliminación se incorporarán al implementar el ciclo de vida completo.

## Alcance

Identidad: registro, login, consulta de sesión, logout, hash Argon2id, token opaco almacenado como hash, expiración, validación de Origin, CSRF por sesión y límites persistidos de intentos. Cuenta individual con rol propietario; invitaciones, organizaciones, recuperación de contraseña, verificación de correo y OIDC se incorporarán cuando se defina su alcance. No hay autoasignación de roles desde el navegador.

Ingesta, perfilado y calidad procesan CSV reales. Las 11 pantallas del ejemplo siguen disponibles como demostración; en datos propios, el análisis, los dashboards, los informes y el copiloto trabajan con resultados calculados. Los archivos reales permiten descargar su original íntegro; las exportaciones del ejemplo permanecen etiquetadas.

Consultar `docs/architecture/implementation-plan.md` para fases y verificación manual.

### Diseño del siguiente incremento — Fase 1

Contratos objetivo: [Fase 1](docs/architecture/phase-1/README.md). Separación de datasets/ejecuciones: [Fase 2](docs/architecture/phase-2.md). Revisión semántica persistida: [Fase 3](docs/architecture/phase-3.md). Planes y catálogo de operaciones: [Fase 4](docs/architecture/phase-4.md). Limpieza supervisada y versiones derivadas: [Fase 5](docs/architecture/phase-5.md). Tablas tipadas y conversiones: [Fase 6](docs/architecture/phase-6.md). Análisis de negocio: [Fase 7](docs/architecture/phase-7.md). Dashboards: [Fase 8](docs/architecture/phase-8.md). Informes y exportaciones: [Fase 9](docs/architecture/phase-9.md). Copiloto de IA: [Fase 10](docs/architecture/phase-10.md). Automatización determinista (11.0 implementada; resto en plan): [Fase 11](docs/architecture/phase-11.md). Nuevas fuentes (plan): [Fase 12](docs/architecture/phase-12.md).

`npm run contracts:check` verifica sus esquemas, ejemplos y casos negativos sin API ni PostgreSQL. Para regenerar exclusivamente los artefactos de diseño: `npm run contracts:examples`. El contrato HTTP vigente continúa en `contracts/openapi/dataflow.json`.

## Contenedor y CI

**Actualizar desde 0.13 / esquema 0011:** 0012 es aditiva (conversaciones y registro de llamadas del copiloto, sin backfill). Instalar la dependencia nueva `anthropic`; el worker no cambia. La IA queda desactivada hasta configurarla. Detalles en [Fase 10](docs/architecture/phase-10.md).

**Actualizar desde 0.12 / esquema 0010:** 0011 es aditiva (informes y PDF generados, sin backfill). Instalar la dependencia nueva `reportlab` y desplegar API y worker juntos: un worker 0.12 no atiende `report_render`. Detalles en [Fase 9](docs/architecture/phase-9.md).

**Actualizar desde 0.11 / esquema 0009:** 0010 es aditiva (dashboards, sin backfill). Desplegar API y worker juntos; planes, ejecuciones, métricas y versiones existentes no cambian. Detalles en [Fase 8](docs/architecture/phase-8.md).

**Actualizar desde 0.10 / esquema 0009:** sin migración. Desplegar API y worker juntos: el catálogo pasa a `analysis-v6` con `analytics.query@2` (comparaciones, ranking y participación); `analytics.query@1`, sus planes guardados y sus resultados no cambian. Detalles en [Fase 7](docs/architecture/phase-7.md).

**Actualizar desde 0.9 / esquema 0008:** 0009 es aditiva (métricas de análisis, sin backfill). Desplegar API y worker juntos: el catálogo pasa a `analysis-v5` con `analytics.query@1`; los diagnósticos y resultados existentes no cambian. Detalles en [Fase 7](docs/architecture/phase-7.md).

**Actualizar desde 0.8 / esquema 0007:** 0008 es aditiva (conjuntos de reglas de calidad, sin backfill). Desplegar API y worker juntos: el catálogo pasa a `analysis-v4` con `quality.evaluate@2`; los diagnósticos existentes no cambian. Detalles en [Fase 6](docs/architecture/phase-6.md).

**Actualizar desde 0.7 / esquema 0006:** 0007 es aditiva (detalle de errores de ejecución, sin backfill). Desplegar API y worker juntos: el catálogo pasa a `analysis-v3`, los planes guardados conservan su versión y su hash, y las versiones, diagnósticos y hashes existentes no cambian. Detalles en [Fase 6](docs/architecture/phase-6.md).

**Actualizar desde 0.6 / esquema 0005:** 0006 es aditiva (aprobaciones y linaje de versiones, sin backfill). Desplegar API y worker juntos: el catálogo pasa a `analysis-v2` y los planes guardados conservan su versión y su hash. Un despliegue invalida las aprobaciones pendientes de aplicar (el hash de entorno cambia), que deben repetir la vista previa. Detalles en [Fase 5](docs/architecture/phase-5.md).

**Actualizar desde 0.5 / esquema 0004:** 0005 es aditiva (tablas nuevas, sin backfill) y no modifica planes ni ejecuciones existentes. Esperar a que terminen los trabajos en curso y desplegar API y worker juntos: un worker 0.5 no reclama ejecuciones `plan`, pero no debe convivir con planes de usuario. Detalles en [Fase 4](docs/architecture/phase-4.md).

**Actualizar desde 0.4 / esquema 0003:** usar el respaldo y ensayo de restauración de [Fase 3](docs/architecture/phase-3.md). 0004 es aditiva, conserva los CSV/resultados existentes y no confirma ni crea contratos semánticos automáticamente.

**Actualizar desde 0.3:** seguir el respaldo y ensayo de restauración de [Fase 2](docs/architecture/phase-2.md). La migración 0003 es aditiva; el cutover exige jobs legacy terminales y verifica hashes. La API abre el recorrido nuevo cuando completa el corte. Los registros históricos incompletos quedan identificados como `legacy_partial`.

```powershell
docker compose -f infrastructure/compose/compose.yaml --profile full up --build -d
```

Frontend en http://localhost:3002 y API en http://127.0.0.1:8000. No iniciar simultáneamente otro servidor en esos puertos. PostgreSQL usa `postgres_data`; API y worker comparten los archivos en `objects_data`. Para detener: `docker compose -f infrastructure/compose/compose.yaml --profile full down`. No añadir `-v` si se quieren conservar los datos. Respaldar ambos volúmenes juntos.

El modo local sin contenedores usa `apps/api/.data/objects` por defecto. Para alternar con el modo completo de Docker sobre la misma base, hay que trasladar los objetos o configurar el mismo almacenamiento compartido; no basta con reutilizar sólo PostgreSQL. Los tests E2E usan almacenamiento y base separados.

Los Dockerfiles ejecutan con usuario sin privilegios. GitHub Actions tiene pipelines separados para backend y frontend, incluyendo integración con PostgreSQL y pruebas de contrato/navegador. Prettier mantiene formato web/documentación; Ruff formatea Python.

La contraseña de Compose es exclusivamente para desarrollo local. En despliegues HTTPS: secretos externos, `DATAFLOW_COOKIE_SECURE=true`, orígenes exactos y un proxy confiable con políticas de red. El rate limit usa la IP de conexión sin confiar en cabeceras reenviadas; detrás de un proxy compartido debe configurarse un control de entrada por cliente real.

## Dependencias

El último `npm install` del incremento 0.3 informó 0 vulnerabilidades. El contrato OpenAPI y el cliente generado se verifican en CI. `apps/api/requirements.lock` fija dependencias del entorno verificado para desarrollo, CI y Docker; al actualizarlas se deben regenerar contratos y repetir pruebas. La versión efectiva de Polars se conserva en cada diagnóstico para reproducibilidad.
