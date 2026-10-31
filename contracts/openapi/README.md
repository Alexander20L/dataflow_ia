# Contrato HTTP

`dataflow.json` se exporta desde FastAPI con `apps/api/scripts/export_openapi.py`.
No editar manualmente. Después ejecutar `npm run api:generate` desde la raíz.
El generador no consulta PostgreSQL. `--check` comprueba drift en CI.
