# DataFlow AI

**API 0.36 — pestañas Dataset, Comprensión, Investigación, Dashboard e Informe y análisis completamente automático con comprensión del negocio, exploración guiada, dashboard adaptado, criterio analítico, investigación e informe (Fases 13 a 28):** la versión se abre en la pestaña **Dataset** (Resumen, Registros paginados en el servidor, perfil de cada Columna, Diccionario con correcciones opcionales que se heredan y nunca cambian el archivo, Calidad por dimensiones con valores fuera de rango, atípicos y filas repetidas sin identificador, y lectura del Archivo, todo calculado una vez sobre el dataset completo). Desde la Fase 23 las correcciones del Diccionario cuentan: la comprensión, la exploración y el dashboard se recalculan con ellas, las columnas con datos personales nunca se envían a la IA y los textos «sin dato» que declares crean una versión derivada. La pestaña **Comprensión** (Fase 24) dice qué representa cada fila, qué columnas son fórmulas de otras (para no presentarlas como hallazgos), cómo se relacionan las columnas (estructurales, estadísticas y temporales, que puedes validar o rechazar) y qué significa cada una, con la confianza y la justificación de la IA; desde la Fase 24B puedes marcar una columna como desconocida y el informe usa tus significados. Todas las presentaciones muestran las cifras con tres decimales como mucho (los cálculos conservan todos). La pestaña **Investigación** (Fase 25) muestra el plan (pregunta, motivo, hipótesis, columnas, método, resultado esperado, prioridad y dependencias), el árbol de investigaciones secundarias que se abren cuando un resultado es interesante, la evidencia de cada resultado (registros considerados, filtros, operación, cifras y ejecución) con su clase (hallazgo relevante o secundario, descriptivo, no concluyente o hipótesis descartada) y el historial; puedes pausarla, cancelarla, reanudarla o volver a investigar. La pestaña **Dashboard** (Fase 26) empieza por indicadores con su unidad (sólo si está declarada), periodo de referencia, comparación con el mes anterior cuando hay base y procedencia; sigue con gráficos adaptados a cada resultado (líneas, barras, histograma, dispersión, mapa de calor, circular o tabla) ordenados por importancia, cada uno con su origen; los filtros por periodo y categoría recalculan con el motor exacto lo que depende de ellos; y puedes guardar una versión personalizada (ocultar, reordenar, elegir indicadores y renombrar) sin perder la automática. La pestaña **Informe** (Fase 27) muestra la vista previa del documento (resumen ejecutivo, descripción del dataset, calidad y metodología, hallazgos principales, investigaciones realizadas, conclusiones y recomendaciones sin causalidad, y anexo de evidencias), te deja aprobar o rechazar cada hallazgo y generar una versión nueva con tu selección, y conserva el historial con su PDF. Desde la Fase 28 el análisis aplica criterio de analista: una fecha que describe a cada registro (como la fecha de ingreso de un empleado) no se trata como línea de tiempo sino que se cuenta por año, los promedios y tasas de grupos con menos de 10 registros no cuentan como hallazgo, las columnas de dos valores (activo, aprobado…) se analizan como tasa en total y por grupo, se reconocen escalas de valoración y no se repite el mismo hallazgo. El resto está en **Análisis**. subes un CSV o un libro de Excel y el sistema lo lee (CSV en UTF-8 o Windows-1252; números con coma decimal y fechas día/mes/año cuando no hay ambigüedad; en un libro elige solo la hoja o tabla principal y su cabecera, y analiza aparte las demás tablas con datos; también tablas de PDF con texto y copias de un solo uso de tablas de SQL Server, sin guardar la contraseña), lo perfila, evalúa su calidad, lo interpreta (la IA describe el negocio a partir de los nombres de las columnas y un perfil agregado, y los datos confirman o no cada relación con correlaciones, V de Cramér o eta sobre todas las filas; el usuario puede marcar, si quiere, qué relaciones le sirven; después la IA propone consultas de un lenguaje cerrado que Python valida y el motor calcula sobre todas las filas, y juzga su relevancia viendo como mucho cien filas de cada resultado) y publica un dashboard con indicadores, gráficos y detalle (además, la IA diseña un dashboard adaptado a esos datos eligiendo secciones, orden y tipo de gráfico de un catálogo cerrado, sin cifras ni código, que Python valida; el usuario puede marcar «Sí va» o «No va» en cada hallazgo y el informe sigue ese orden), sin formularios, aprobaciones ni configuración. Después, una investigación acotada sigue los hallazgos (meses atípicos, variación interanual, grupo principal): las reglas proponen siempre y, si la IA está configurada, también ella, en un esquema cerrado que Python valida y el motor calcula; al final la IA explica hallazgos y seguimientos con cifras verificadas por su evidencia. Cada carga termina en un informe PDF automático con los hallazgos, la investigación, la calidad y las limitaciones, con cada cifra referida a su evidencia; la interfaz muestra primero un resumen con el progreso por etapas. Sin IA o ante errores, los hallazgos y el dashboard siguen disponibles. Al modelo sólo se envían cifras agregadas acotadas, sus etiquetas y limitaciones; nunca filas. El original y cada versión son inmutables. [Decisión (ADR-026)](docs/adr/026-fully-automatic-single-path.md) · [Fase 13 y 13B](docs/architecture/phase-13.md) · [ADR-027](docs/adr/027-excel-and-ai-without-configuration.md) · [ADR-028](docs/adr/028-upload-queue.md) · [Fase 14 y ADR-031](docs/architecture/phase-14.md) · [Fase 15 y ADR-032](docs/architecture/phase-15.md) · [Fase 16 y ADR-033](docs/architecture/phase-16.md) · [Fase 17 y ADR-034](docs/architecture/phase-17.md) · [Fase 18 y ADR-035](docs/architecture/phase-18.md) · [Fase 19 y ADR-036](docs/architecture/phase-19.md) · [Fase 20 y ADR-037](docs/architecture/phase-20.md) · [Fase 21 y ADR-038](docs/architecture/phase-21.md) · [Fase 22 y ADR-039](docs/architecture/phase-22.md) · [Fase 23 y ADR-040](docs/architecture/phase-23.md) · [Fase 24 y ADR-041](docs/architecture/phase-24.md) · [Fase 24B y ADR-042](docs/architecture/phase-24b.md) · [Fase 25 y ADR-043](docs/architecture/phase-25.md) · [Fase 26 y ADR-044](docs/architecture/phase-26.md) · [Fase 27 y ADR-045](docs/architecture/phase-27.md) · [Fase 28 y ADR-046](docs/architecture/phase-28.md) · [analista automático](docs/architecture/automatic-analyst.md).

Las Fases 4 a 10 construyeron un recorrido supervisado (semántica, planes, limpieza con aprobación, reglas, métricas, dashboards editables, informes y copiloto con botones). Desde la Fase 13 ya no forma parte del producto: se conservan sus motores (limpieza, calidad, análisis con evidencia), que el recorrido automático incorporará en la Fase 14, y sus tablas históricas.

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

### Explicación con IA (opcional)

Se activa sola en cuanto hay una clave (`DATAFLOW_AI_PROVIDER=auto`, el valor por defecto); sin clave queda desactivada y el producto funciona igual. En local, en `apps/api/.env` (ignorado por git; nunca en el repositorio ni en el frontend):

```sh
DATAFLOW_AI_API_KEY=<tu clave de la API de Anthropic>
# Opcional: DATAFLOW_AI_MODEL=claude-opus-5-5 · DATAFLOW_AI_EFFORT=low
```

Con Docker, guarda la clave en un archivo fuera del repositorio (o en `infrastructure/compose/secrets/`, que git ignora) y arranca con `DATAFLOW_AI_API_KEY_SECRET_FILE=<ruta del archivo>`: se monta como secreto en `/run/secrets/ai_api_key`. Límites de uso por usuario y día (tokens) y por proyecto y mes (costo estimado) en `apps/api/.env.example`. `DATAFLOW_AI_PROVIDER=disabled` la apaga aunque haya clave y `fake` usa un proveedor determinista sin red (pruebas y E2E; pytest fuerza `disabled` si no se indica otro). Casos reales opcionales contra el modelo: `DATAFLOW_AI_LIVE_TESTS=1` con la clave configurada y `pytest apps/api/tests/ai/test_ai_live.py` (generan costo).
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

Crear cuenta → Nuevo análisis → seleccionar un CSV o un `.xlsx` → el original se conserva → procesamiento en cola → **Tu análisis automático** (indicadores, gráficos, lectura de las columnas y detalle) → **Explicación automática IA** si está activada. No hay pasos intermedios ni decisiones que tomar.

Prueba con `examples/ventas_calidad.csv`: 6 registros, 5 columnas, una celda vacía, una fila duplicada adicional y una celda de espacios. Completitud: 96,67 %. `examples/ventas.xlsx` produce las mismas cifras.

Los proyectos se guardan en PostgreSQL con propietario, revisión y eventos de auditoría. La búsqueda y paginación se realizan en el backend. Un usuario no puede listar, leer, editar ni archivar proyectos ajenos. Ediciones obsoletas devuelven 409.

### CSV admitidos

- UTF-8 con o sin BOM; coma, punto y coma o tabulador, siempre con detección automática (la API conserva la opción explícita).
- Hasta 5 MiB, 100.000 registros, 128 columnas y 10.000 caracteres por campo. Cabecera única y no vacía; errores estructurales se muestran sin publicar resultados parciales.
- Original byte a byte y SHA-256. Copia Parquet con texto nullable: conserva ceros iniciales y espacios; campos vacíos se representan como nulos. Los tipos sugeridos son heurísticos y no convierten los valores.
- Reglas: vacíos por columna, duplicados posteriores a su primera aparición y campos sólo con espacios/tabuladores/saltos. Completitud mide celdas no vacías; no una calidad universal.
- Cuota inicial de 100 MiB de originales por cuenta; una carga activa por proyecto y tres por cuenta. Parquet y conectores se integrarán después.

Las cargas se confirman con metadatos y trabajo en una transacción PostgreSQL. El worker usa leases, fencing, máximo tres intentos y subproceso con timeout. Un intento antiguo o cancelado no publica artefactos. Puedes cerrar el navegador durante el procesamiento.

Las versiones anteriores al análisis automático (sin dashboard guardado) muestran su diagnóstico técnico: perfil por columna, incidencias de calidad y vista previa. Las versiones derivadas por limpieza conservan su linaje y su original de origen.

Sólo el tema se conserva en localStorage (`dataflow-ui-v2`).

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

Ingesta (CSV y Excel), perfilado, calidad, interpretación por reglas, dashboard automático y explicación con IA opcional sobre archivos propios. Cada versión permite descargar su original íntegro y exportar su tabla en CSV estándar o Excel regional.

Consultar `docs/architecture/implementation-plan.md` para fases y verificación manual.

### Diseño del siguiente incremento — Fase 1

Contratos objetivo: [Fase 1](docs/architecture/phase-1/README.md). Separación de datasets/ejecuciones: [Fase 2](docs/architecture/phase-2.md). Revisión semántica persistida: [Fase 3](docs/architecture/phase-3.md). Planes y catálogo de operaciones: [Fase 4](docs/architecture/phase-4.md). Limpieza supervisada y versiones derivadas: [Fase 5](docs/architecture/phase-5.md). Tablas tipadas y conversiones: [Fase 6](docs/architecture/phase-6.md). Análisis de negocio: [Fase 7](docs/architecture/phase-7.md). Dashboards: [Fase 8](docs/architecture/phase-8.md). Informes y exportaciones: [Fase 9](docs/architecture/phase-9.md). Copiloto de IA: [Fase 10](docs/architecture/phase-10.md). Automatización determinista (pipeline por política retirado en la Fase 13): [Fase 11](docs/architecture/phase-11.md). Nuevas fuentes (Excel implementado; SQL Server y PDF en plan): [Fase 12](docs/architecture/phase-12.md). Un solo recorrido automático, con Excel e IA sin configuración y cola de cargas: [Fase 13, 13B y 13C](docs/architecture/phase-13.md).

`npm run contracts:check` verifica sus esquemas, ejemplos y casos negativos sin API ni PostgreSQL. Para regenerar exclusivamente los artefactos de diseño: `npm run contracts:examples`. El contrato HTTP vigente continúa en `contracts/openapi/dataflow.json`.

## Contenedor y CI

**Actualizar desde 0.35:** sin migración. Las cargas nuevas usan la comprensión `business-comprehension-v4` (añade `dated_attributes`), la inspección `dataset-inspection-v3` (añade `date_role` y `date_role_reason` por columna y el rango `rating`) y la investigación `investigation-v3` con la operación `exploration.explore@3` (consultas `rate` y `cohort` con `target` y `target_value`, relevancia `relevance-v2`). Las versiones analizadas antes se siguen leyendo con sus reglas; para aplicar las nuevas, vuelve a cargar el archivo. Desplegar API y worker juntos. Detalles en [Fase 28](docs/architecture/phase-28.md).

**Actualizar desde 0.34:** sin migración. Las cargas nuevas ya no ejecutan el seguimiento de hallazgos de la Fase 16: el informe `delivery.report@2` (`automatic-report-v2`, prompt `report-narrative` v1) se encola al publicarse el dashboard, su artefacto es el documento (`report_document`) y el PDF se dibuja al descargarlo. Las marcas del dashboard pasan a ser la revisión del informe y ya no lo regeneran: la versión nueva se pide con `POST /versions/{id}/report/versions`. Rutas nuevas: `GET /versions/{id}/report/history`, `GET /versions/{id}/report/versions/{execution_id}` y `GET`/`POST /versions/{id}/report/review`; `GET /report` añade `number` y `document`, y `GET /report.pdf` admite `execution_id`. Los informes anteriores se siguen leyendo. Desplegar API y worker juntos. Detalles en [Fase 27](docs/architecture/phase-27.md).

**Actualizar desde 0.33:** migración 0027 (`dashboard_customizations`, aditiva). Las cargas nuevas diseñan el dashboard con `delivery.dashboard@2` (`dashboard-design-v2`, prompt de diseño v2): el artefacto añade `items` (con su origen), `indicators`, `computed`, `filters`, `total_rows`, `partial` y `notice`; el motor de la exploración calcula dos tipos internos del dashboard (`distribution` y `scatter`) que la investigación no propone ni acepta. Rutas nuevas: `POST /versions/{id}/dashboard/filter` y `POST /versions/{id}/dashboard/custom`; `GET /versions/{id}/dashboard` añade `custom` y `custom_dropped`. Los dashboards anteriores se siguen leyendo, sin filtros ni personalización. Desplegar API y worker juntos. Detalles en [Fase 26](docs/architecture/phase-26.md).

**Actualizar desde 0.32:** migración 0026 (`investigation_controls`, aditiva). Las cargas nuevas se investigan con `exploration.explore@2` (`investigation-v2`, lenguaje `explore-v2` con evolución mensual, comparación de periodos y valores atípicos; prompts de exploración v2). El artefacto `exploration` añade `nodes`, `stopped`, `resumed_from`, `trigger` y `consumption` y conserva `results` y `proposals`, así que el dashboard y el informe lo leen igual. Rutas nuevas: `GET /versions/{id}/exploration/history` y `POST /versions/{id}/exploration/control`; `GET /versions/{id}/exploration` admite `execution_id`. Desplegar API y worker juntos. Detalles en [Fase 25](docs/architecture/phase-25.md).

**Actualizar desde 0.31:** migración 0025 (`column_meaning_marks`, aditiva). `POST /versions/{id}/comprehension/meanings` admite `unknown` y pide otra versión del informe; los significados añaden `reason` y `unknown` (prompt de comprensión v3). El informe usa los significados del usuario y muestra las cifras con tres decimales como mucho; los artefactos y la API no cambian sus cifras. Desplegar API y worker juntos. Detalles en [Fase 24B](docs/architecture/phase-24b.md).

**Actualizar desde 0.30:** migración 0024 (`column_meanings`, aditiva). La comprensión pasa a `business-comprehension-v3` en las cargas nuevas (grano, fórmulas, misma entidad, periodo, medidas y dimensiones; familia y estado de cada relación; confianza de los significados, prompt v2). `POST /versions/{id}/comprehension/meanings` es nuevo, y `POST /versions/{id}/comprehension/feedback` rehace la exploración, el dashboard y el informe. Desplegar API y worker juntos. Detalles en [Fase 24](docs/architecture/phase-24.md).

**Actualizar desde 0.29:** migración 0023 (`column_annotation_details`, aditiva). La inspección pasa a `dataset-inspection-v2` y la comprensión a `business-comprehension-v2` en las cargas nuevas; las versiones anteriores conservan las suyas. `POST /versions/{id}/dictionary` admite `null_tokens` y `personal`, y la vista de la inspección añade `recalculation`. Nuevo tipo de ejecución `null_cleaning` (textos declarados como nulos → versión derivada analizada como una carga). Desplegar API y worker juntos. Detalles en [Fase 23](docs/architecture/phase-23.md).

**Actualizar desde 0.28:** migración 0022 (`column_annotations`, aditiva). Al publicarse cada carga se encola un trabajo `inspection` (sin IA): `GET /versions/{id}/inspection` y `POST /versions/{id}/dictionary`. `GET /versions/{id}/preview` admite `sort` (identificador de columna), `descending` y `search` (parámetros opcionales; responde con `RecordsPage`, los campos de antes más `column_ids`, `sort`, `descending` y `search`). Si el separador detectado no da registros del mismo ancho, se vuelve a detectar sin las líneas en blanco. Las versiones anteriores responden `unavailable`. Desplegar API y worker juntos. Detalles en [Fase 22](docs/architecture/phase-22.md).

**Actualizar desde 0.27:** migración 0021 (`finding_feedback`, aditiva). Al publicarse la exploración se encola un trabajo `dashboard`: `GET /versions/{id}/dashboard` y `POST /versions/{id}/dashboard/feedback`. El informe se reclama el último de la cola y, tras cada marca, se genera una versión nueva (la anterior se sirve con `updating: true` mientras tanto). La exploración y el dashboard responden `queued` (con `execution_id` nulo) mientras la cadena anterior sigue en marcha. Una llamada más a la IA por carga si está configurada. Desplegar API y worker juntos. Detalles en [Fase 21](docs/architecture/phase-21.md).

**Actualizar desde 0.26:** sin migración. Al publicarse la comprensión se encola un trabajo `exploration` (consultas `explore-v1` de reglas e IA): `GET /versions/{id}/exploration`. Cada carga hace hasta dos llamadas más a la IA si está configurada. Las versiones anteriores no tienen exploración (404 `EXPLORATION_NOT_AVAILABLE`). Desplegar API y worker juntos. Detalles en [Fase 20](docs/architecture/phase-20.md).

**Actualizar desde 0.25 / esquema 0019:** 0020 es aditiva (tabla `comprehension_feedback`, inmutable, sin backfill). Tras cada carga con interpretación analítica se encola un trabajo `comprehension` antes de la investigación: `GET /versions/{id}/comprehension` y la valoración opcional `POST /versions/{id}/comprehension/feedback`. Cada carga hace una llamada más a la IA si está configurada. Las versiones anteriores no tienen comprensión (404 `COMPREHENSION_NOT_AVAILABLE`). Desplegar API y worker juntos. Detalles en [Fase 19](docs/architecture/phase-19.md).

**Actualizar desde 0.24:** sin migración. Las cargas nuevas usan `analysis-v13`: `ingestion.read_csv@2` (codificación UTF-8 o Windows-1252 fijada en el plan y valores regionales con `regional-values-v1`) y `ingestion.read_xlsx@2`. Un libro sin hoja pedida usa `xlsx-selection-v2`: además de la versión principal, registra hasta cuatro versiones más (una por tabla con datos) que comparten el original. `GET /versions/{id}/reading` explica la lectura y los cambios de columnas respecto de la versión anterior del mismo archivo; el informe incluye ambas cosas. También `POST /projects/{id}/imports/pdf` (`ingestion.read_pdf@1`) y `POST /projects/{id}/imports/sqlserver` (copia de un solo uso; sólo servidores de `DATAFLOW_SQLSERVER_ALLOWED_HOSTS`, vacío = desactivado). Instalar las dependencias nuevas `pymssql` y `pdfplumber`. Las versiones anteriores no se recalculan. Desplegar API y worker juntos: un worker 0.24 no atiende las lecturas nuevas. Detalles en [Fase 18](docs/architecture/phase-18.md).

**Actualizar desde 0.23:** sin migración. Al publicarse una investigación se encola un trabajo `automatic_report` que genera el informe PDF (`GET /versions/{id}/report` y `/report.pdf`); `GET /versions/{id}/progress` da el estado por etapas. Las versiones anteriores no tienen informe (404 `REPORT_NOT_AVAILABLE`). Las tablas sin uso de las Fases 4–10 se conservan como archivo histórico. Desplegar API y worker juntos. Detalles en [Fase 17](docs/architecture/phase-17.md).

**Actualizar desde 0.22:** sin migración. Tras cada carga con hallazgos se encola un trabajo `investigation` (reglas + propuestas de la IA validadas + explicación de los hallazgos) que sustituye, para esas cargas, a la explicación del dashboard: `GET /versions/{id}/investigation`. Las versiones anteriores conservan su explicación (404 `INVESTIGATION_NOT_AVAILABLE`). Límites por entorno: `DATAFLOW_INVESTIGATION_MAX_ITERATIONS`, `_MAX_AI_CALLS`, `_MAX_SECONDS` y `_MAX_COST_USD`. Desplegar API y worker juntos. Detalles en [Fase 16](docs/architecture/phase-16.md).

**Actualizar desde 0.21:** sin migración. Las cargas nuevas usan `analysis-v12`: el paso `analytics.automatic@1` guarda un plan analítico y hallazgos con evidencia (`GET /versions/{id}/automatic-analysis`). Las versiones anteriores no se recalculan (404 `AUTOMATIC_ANALYSIS_NOT_AVAILABLE`). Desplegar API y worker juntos. Detalles en [Fase 15](docs/architecture/phase-15.md).

**Actualizar desde 0.20:** sin migración. Las cargas nuevas usan el catálogo `analysis-v11`: `understanding.profile@4` (interpretación analítica, dashboard por medidas) y `quality.evaluate@3` (hallazgos con análisis afectados en `quality.analytical`). Las versiones anteriores conservan sus resultados; no se recalculan. Desplegar API y worker juntos: un worker 0.20 no atiende los pasos nuevos. Detalles en [Fase 14](docs/architecture/phase-14.md).

**Actualizar desde 0.19:** sin migración. Las cargas ya no se rechazan con `PROJECT_BUSY` ni con `QUEUE_LIMIT` por tener 3 trabajos activos: se aceptan (202) y esperan en cola; `QUEUE_LIMIT` sólo aparece con 50 trabajos pendientes. Detalles en [Fase 13C](docs/architecture/phase-13.md#fase-13c--las-cargas-esperan-en-cola).

**Actualizar desde 0.18:** sin migración. `DATAFLOW_AI_PROVIDER` pasa a `auto` por defecto: si el entorno ya tiene una clave, la explicación con IA se activa; para mantenerla apagada, fija `disabled`. `uploadXlsx` admite omitir `sheet` (el sistema elige y lo informa en `source_selection`); las llamadas con `sheet` no cambian. Detalles en [Fase 13B](docs/architecture/phase-13.md#fase-13b--excel-e-ia-sin-configuración).

**Actualizar desde 0.17 / esquema 0018:** 0019 **no es aditiva**: elimina las tablas del pipeline por política (0013–0017) y sus datos (políticas, mapeos, ejecuciones del pipeline, sesión de análisis). Haz una copia de seguridad antes si los necesitas. Las tablas de las Fases 3–10 y 11F se conservan. Desplegar API y worker juntos: el worker ya no avanza pipelines ni atiende `report_render`. Detalles en [Fase 13](docs/architecture/phase-13.md).

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
