# Anexo D — Manual de instalación y reproducibilidad

## D.1 Requisitos

| Herramienta                                | Versión usada                                                  |
| ------------------------------------------ | -------------------------------------------------------------- |
| Git                                        | cualquiera reciente                                            |
| Python                                     | **3.12** (3.12.10; no usar 3.13+ para exportar OpenAPI)        |
| Node.js                                    | 24                                                             |
| Docker Desktop / Docker Engine con Compose | PostgreSQL 17                                                  |
| Sistema                                    | Windows 10/11, Linux o macOS (las órdenes están en PowerShell) |
| Clave de Anthropic                         | opcional (sin clave, el sistema funciona sin textos de IA)     |

## D.2 Instalación local

```powershell
git clone https://github.com/Alexander20L/dataflow_ia.git
cd dataflow_ia
npm install
docker compose -f infrastructure/compose/compose.yaml up -d postgres
```

```powershell
Push-Location apps/api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e ".[dev]"
Copy-Item .env.example .env
Pop-Location
```

Para activar la IA, abrir `apps/api/.env` y escribir la clave en `DATAFLOW_AI_API_KEY=` (el archivo está
ignorado por git). Para bases de datos, añadir los servidores permitidos en
`DATAFLOW_POSTGRESQL_ALLOWED_HOSTS` / `DATAFLOW_SQLSERVER_ALLOWED_HOSTS`.

## D.3 Ejecución

```powershell
Push-Location apps/api; .\.venv\Scripts\python.exe -m dataflow.bootstrap.run --with-worker; Pop-Location
```

```powershell
npm run dev --workspace @dataflow/web -- --port 3002
```

Abrir <http://localhost:3002>, crear una cuenta y subir un archivo de `examples/` (por ejemplo los cinco
CSV de `examples/relacionadas/` con «Cargar varios archivos relacionados»). La API aplica las migraciones
al arrancar.

Alternativa con contenedores (API, worker y web): `docker compose -f infrastructure/compose/compose.yaml
--profile full up -d`.

## D.4 Batería de verificación

```powershell
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -q
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/src apps/api/tests apps/api/migrations apps/api/scripts
apps/api/.venv/Scripts/python.exe -m ruff format --check apps/api
Push-Location apps/api; .venv/Scripts/python.exe -m mypy; Pop-Location
npm run typecheck; npm run lint; npm run build; npm run format:check; npm run contracts:check
apps/api/.venv/Scripts/python.exe apps/api/scripts/export_openapi.py --check
apps/api/.venv/Scripts/python.exe apps/api/scripts/prepare_e2e_db.py
npm run test:e2e
```

## D.5 Reproducir la evaluación del TDDR

1. **Detección de relaciones** (sin base de datos, ~8 s):

   ```powershell
   apps/api/.venv/Scripts/python.exe docs/tddr/bench/relations_benchmark.py > docs/tddr/bench/relations_results.json
   ```

2. **Rendimiento de la API**: crear una base aparte y arrancar la API con el proveedor de IA
   determinista en el puerto 8011.

   ```powershell
   docker exec dataflow-postgres-1 psql -U dataflow -d postgres -c "CREATE DATABASE dataflow_bench"
   ```

   ```powershell
   $env:DATAFLOW_DATABASE_URL="postgresql+psycopg://dataflow:dataflow_local@127.0.0.1:55432/dataflow_bench"; $env:DATAFLOW_STORAGE_PATH=".data/bench-objects"; $env:DATAFLOW_AI_PROVIDER="fake"; $env:DATAFLOW_ALLOWED_ORIGINS='["http://localhost:3002","http://localhost:3005"]'; Push-Location apps/api; .\.venv\Scripts\python.exe -m dataflow.bootstrap.run --port 8011 --with-worker
   ```

   ```powershell
   apps/api/.venv/Scripts/python.exe docs/tddr/bench/api_benchmark.py http://127.0.0.1:8011 > docs/tddr/bench/api_results.json
   ```

3. **Capturas de pantalla**: con la API anterior, arrancar la web contra ella y ejecutar el script.

   ```powershell
   $env:API_INTERNAL_URL="http://127.0.0.1:8011"; npm run dev --workspace @dataflow/web -- --port 3005
   ```

   ```powershell
   Push-Location apps/web; node ../../docs/tddr/bench/screens.mjs http://localhost:3005; Pop-Location
   ```

Las semillas son fijas (2026 para los esquemas; el número de filas para los CSV de escalabilidad), así que
la exactitud es idéntica en cada ejecución; los tiempos dependen del equipo.

## D.6 Despliegue en producción

Guía completa: [`docs/operations/deployment.md`](../../operations/deployment.md) (ADR-052).
Resumen: preparar un VPS Ubuntu 24.04 con `infrastructure/production/provision.sh`; definir en GitHub el
entorno `production` (`DEPLOY_HOST`, clave SSH, dominio); cada fusión en `main` compila las imágenes en
GitHub Actions, las publica en GHCR y ejecuta `deploy.sh` por SSH (espera salud, comprueba por HTTPS y
vuelve a la versión anterior si falla). Sin servidor, `infrastructure/compose/tunnel.ps1` publica el
equipo local con un túnel de Cloudflare.
