# DataFlow AI

**API 0.24 — análisis completamente automático con criterio analítico, investigación e informe (Fases 13 a 17):** subes un CSV o un libro de Excel y el sistema lo lee (en un libro elige solo la hoja o tabla principal y su cabecera), lo perfila, evalúa su calidad, lo interpreta y publica un dashboard con indicadores, gráficos y detalle, sin formularios, aprobaciones ni configuración. Después, una investigación acotada sigue los hallazgos (meses atípicos, variación interanual, grupo principal): las reglas proponen siempre y, si la IA está configurada, también ella, en un esquema cerrado que Python valida y el motor calcula; al final la IA explica hallazgos y seguimientos con cifras verificadas por su evidencia. Cada carga termina en un informe PDF automático con los hallazgos, la investigación, la calidad y las limitaciones, con cada cifra referida a su evidencia; la interfaz muestra primero un resumen con el progreso por etapas. Sin IA o ante errores, los hallazgos y el dashboard siguen disponibles. Al modelo sólo se envían cifras agregadas acotadas, sus etiquetas y limitaciones; nunca filas. El original y cada versión son inmutables. [Decisión (ADR-026)](docs/adr/026-fully-automatic-single-path.md) · [Fase 13 y 13B](docs/architecture/phase-13.md) · [ADR-027](docs/adr/027-excel-and-ai-without-configuration.md) · [ADR-028](docs/adr/028-upload-queue.md) · [Fase 14 y ADR-031](docs/architecture/phase-14.md) · [Fase 15 y ADR-032](docs/architecture/phase-15.md) · [Fase 16 y ADR-033](docs/architecture/phase-16.md) · [Fase 17 y ADR-034](docs/architecture/phase-17.md) · [analista automático](docs/architecture/automatic-analyst.md).

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
