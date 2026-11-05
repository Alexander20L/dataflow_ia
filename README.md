# DataFlow AI

Plataforma de análisis de datos supervisado. **API 0.6 / Fase 4:** planes versionados con operaciones de catálogo, validación con requisitos pendientes y ejecución sobre la tabla exacta. Incluye el contexto semántico de Fase 3 y CSV, originales, perfilado y calidad reales. Limpieza y etapas posteriores continúan como demostración independiente.

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

El fixture contiene 240 ventas y 8 importes nulos. Su limpieza demostrativa crea una vista v2 de 232 registros y mantiene v1 intacta. No se atribuyen esos resultados a archivos propios. Los CSV reales tienen sus propias versiones y diagnósticos, y no se limpian automáticamente. Las conexiones externas y la IA real están pendientes.

### CSV admitidos

- UTF-8 con o sin BOM; coma, punto y coma o tabulador, con detección automática u opción explícita.
- Hasta 5 MiB, 100.000 registros, 128 columnas y 10.000 caracteres por campo. Cabecera única y no vacía; errores estructurales se muestran sin publicar resultados parciales.
- Original byte a byte y SHA-256. Copia Parquet con texto nullable: conserva ceros iniciales y espacios; campos vacíos se representan como nulos. Los tipos sugeridos son heurísticos y no convierten los valores.
- Reglas: vacíos por columna, duplicados posteriores a su primera aparición y campos sólo con espacios/tabuladores/saltos. Completitud mide celdas no vacías; no una calidad universal.
- Cuota inicial de 100 MiB de originales por cuenta; una carga activa por proyecto y tres por cuenta. XLSX/Parquet y conectores se integrarán después.

Las cargas se confirman con metadatos y trabajo en una transacción PostgreSQL. El worker usa leases, fencing, máximo tres intentos y subproceso con timeout. Un intento antiguo o cancelado no publica artefactos. Puedes cerrar el navegador durante el procesamiento.

En cada CSV procesado, **Planes y ejecuciones** permite armar un plan con operaciones del catálogo (perfil, calidad), guardarlo como revisión inmutable sobre una tabla identificada por su hash y ejecutarlo. Un plan incompleto muestra qué le falta y no se ejecuta. Cambiar la versión predeterminada no altera la entrada de un plan. Cada ejecución conserva su plan, resultados e historial. El diagnóstico baseline permanece fijo; ejecutar análisis no crea otra versión del archivo. [Documentación Fase 4](docs/architecture/phase-4.md).

En **Entendimiento → Revisión semántica** declara filas, roles, interpretación, claves, unidades/moneda y nulos. Guarda revisiones parciales y consulta su historial. No convierte ni limpia valores. Un plan puede fijar una revisión exacta o continuar sin contrato para análisis técnicos. [Documentación Fase 3](docs/architecture/phase-3.md).

Sólo el tema y la limpieza del ejemplo se conservan en localStorage (`dataflow-ui-v2`). Restablecer la demo no elimina proyectos de la cuenta. El almacenamiento legado `dataflow-demo-v1` se conserva sin importar sus proyectos automáticamente: no se atribuyen datos locales a una cuenta sin una migración explícita.

## Estructura

- `apps/web`: aplicación Next.js independiente, funcionalidades en `src/features`.
- `apps/api`: monolito modular FastAPI; casos de uso con puertos, repositorios SQL y routers separados.
- `packages/api-client`: cliente tipado desde OpenAPI, sin tipos HTTP duplicados a mano.
- `contracts/openapi`: instantánea versionada del contrato.
- `infrastructure/compose`: PostgreSQL y despliegue local completo.
- `docs/architecture`: arquitectura, contratos y hoja de ruta.
- `docs/adr`: decisiones arquitectónicas.

El worker reutiliza el monolito modular, sin duplicar reglas. El frontend y la API son desplegables independientemente. El adaptador local de objetos es de desarrollo; S3 y retención/eliminación se incorporarán al implementar el ciclo de vida completo.

## Alcance

Identidad: registro, login, consulta de sesión, logout, hash Argon2id, token opaco almacenado como hash, expiración, validación de Origin, CSRF por sesión y límites persistidos de intentos. Cuenta individual con rol propietario; invitaciones, organizaciones, recuperación de contraseña, verificación de correo y OIDC se incorporarán cuando se defina su alcance. No hay autoasignación de roles desde el navegador.

Ingesta, perfilado y calidad procesan CSV reales. Las 11 pantallas del ejemplo siguen disponibles como demostración; el editor BI, el informe y el copiloto no analizan todavía datasets propios. Los archivos reales permiten descargar su original íntegro; las exportaciones del ejemplo permanecen etiquetadas.

Consultar `docs/architecture/implementation-plan.md` para fases y verificación manual.

### Diseño del siguiente incremento — Fase 1

Contratos objetivo: [Fase 1](docs/architecture/phase-1/README.md). Separación de datasets/ejecuciones: [Fase 2](docs/architecture/phase-2.md). Revisión semántica persistida: [Fase 3](docs/architecture/phase-3.md). Planes y catálogo de operaciones: [Fase 4](docs/architecture/phase-4.md). Limpieza, aprobaciones y derivadas se incorporarán en fases posteriores.

`npm run contracts:check` verifica sus esquemas, ejemplos y casos negativos sin API ni PostgreSQL. Para regenerar exclusivamente los artefactos de diseño: `npm run contracts:examples`. El contrato HTTP vigente continúa en `contracts/openapi/dataflow.json`.

## Contenedor y CI

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
