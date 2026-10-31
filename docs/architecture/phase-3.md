# Fase 3 — Entendimiento semántico

API 0.5. [ADR-013](../adr/013-semantic-revisions.md). Understanding conserva contexto y revisiones, sin transformar contenido ni producir versiones derivadas.

## Recorrido e interfaz

CSV procesado → Entendimiento → perfil técnico → revisión semántica → confirmar/corregir/dejar pendiente → guardar → historial → elegir revisión al ejecutar.

Definiciones: descripción del dataset, significado de cada fila, roles, interpretación/formato, descripción de columnas, unidad/moneda, política declarada de nulos y clave simple/compuesta. El tipo físico permanece igual.

Editor parcial, detalles por columna, observaciones de clave, historial de sólo lectura y diferencias con la cabeza. Se distingue origen/estado de sugerencias. Rechazar conserva la propuesta como rechazada; no se considera confirmada. Los conteos de clave corresponden a lo guardado, no se inventan para el borrador.

Cambios sin guardar se avisan al navegar, recargar, cerrar o cambiar etapa/versión/carga. Un conflicto mantiene el borrador y ofrece cargar explícitamente lo nuevo del servidor. La selección de contexto en ejecuciones es opcional y muestra las últimas 20 revisiones; el historial tiene paginación completa. No se elige automáticamente la nueva cabeza.

## API

| Ruta                                                   | Función                                                        |
| ------------------------------------------------------ | -------------------------------------------------------------- |
| GET `/api/v1/representations/{id}/understanding`       | Esquema, perfil, sugerencias, cabeza, editable y observaciones |
| GET `/api/v1/representations/{id}/semantic-contracts`  | Referencias paginadas                                          |
| GET `/api/v1/semantic-contracts/{revision_id}`         | Revisión exacta                                                |
| POST `/api/v1/representations/{id}/semantic-contracts` | Guardado con expected_revision, hash, draft e Idempotency-Key  |

Sesión/propietario en lectura y escritura, CSRF/Origin en mutaciones. El servidor reconstruye hechos técnicos y asigna actor/procedencia; no acepta cambios de nombres/ordinales/tipos físicos. Conflicto: 409; referencia ajena/inexistente: 404; campos incoherentes: 422. Archivados sólo se consultan. Un replay puede recuperar una decisión existente sin editarla.

## Persistencia y procedencia

`semantic_families`: representación, versión, esquema y cabeza. `semantic_revisions`: contenido/hash/actor/fecha. `semantic_save_requests`: identidad de solicitudes y revisión resultante. Revisión, cabeza y auditoría se confirman en una sola transacción. Locks/constraints protegen concurrencia, incluida la primera revisión. Un no-op no incrementa revisión ni cambia fechas de confirmaciones intactas.

Descripciones/unidades normalizan espacios exteriores y vacío→null de metadatos, sin tocar datos. Tokens nulos preservan cadenas exactas. Sugerencias usan reglas deterministas; grano/moneda no se inventan. Confirmar claves con duplicados es válido como intención, y se advierte el problema sin borrar registros.

## Ejecuciones

`AnalysisRequest.semantic_ref` opcional. Sin referencia conserva huella/compatibilidad 0.4. Con ella, plan e idempotencia fijan ID/revisión/hash y el worker valida TableRef exacto antes de calcular. Una revisión histórica de la misma tabla es válida; otra tabla/versión requiere revisión propia aunque coincidan nombres o bytes.

Perfil/calidad no aplican las políticas declaradas ni cambian cifras por confirmar un rol. El contexto acompaña al plan para planificación/limpieza posteriores.

## Límites

128 columnas; descripciones de dataset 2000 caracteres, fila 500 y columna 1000; 20 tokens únicos de hasta 100 caracteres. Proxy de guardado semántico hasta 2 MiB; otros JSON conservan 64 KiB y CSV 5 MiB. Backend valida campos/esquema. Sin IA, interpretación regional automática, conversión ni KPIs de negocio nuevos.

## Despliegue

Construir imágenes. Esperar trabajos. `python tools/backup_phase3.py --stop` (exclusivo origen 0003) toma copias coordinadas y pausa servicios. `python tools/verify_phase3_backup.py "<directorio>"` restaura en DB/volumen aleatorios, aplica 0004 y verifica mismo inventario/hashes con cero revisiones creadas. Arrancar Compose full: API aplica Alembic antes de tráfico y worker nuevo comprueba referencias. No mezclar workers viejos con planes semánticos.

0004 añade tablas/índices/triggers sin backfill de decisiones. Guardar revisiones impide downgrade que las perdería. Herramientas guardan filesystem anterior y copias separadas de metadatos/objetos; no son un sistema genérico de backups.

### Verificación local — 2026-10-29

Despliegue Docker completado con API 0.5.0. Respaldo previo en `.data/backups/20261029T212430Z-phase3/`, con manifiesto y `restore-verification.json`: restauración aislada 0003 → 0004 verificada antes de actualizar la base activa.

El inventario restaurado y el desplegado coinciden: 3 versiones, 5 ejecuciones, 12 artefactos, 4 planes y 15 objetos con hashes verificados. Cero revisiones semánticas creadas automáticamente. `alembic check` sin diferencias; readiness de API y HTTP de web correctos; worker iniciado.

## Pruebas

Parcialidad, no-op/replay, procedencia, conflictos reales entre sesiones, referencias históricas, otra tabla/usuario/hash, campos falsificados, moneda/unidad/formato/tokens, originales/diagnósticos intactos, ceros iniciales y claves duplicadas. Migración desde 0003 y fences reales. Navegador: revisión/historial, análisis con revisión antigua, conflicto preservando borrador y descarte explícito.
