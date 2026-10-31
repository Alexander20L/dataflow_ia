# Incremento 0.2 — Identidad y proyectos conectados

Implementado: registro/login/logout/me, cookies y CSRF, proyectos por propietario, consulta individual, búsqueda literal insensible a mayúsculas, paginación acotada, actualización optimista y archivo. Auditoría de escrituras de proyectos en la misma transacción. Health/readiness, errores estructurados y correlation_id. Alembic crea tablas explícitas; no hay create_all al iniciar producción.

Los puertos de proyectos/identidad están en application; los dominios no importan frameworks. El registro de modelos y la inyección se realizan en bootstrap. Proyectos usa la interfaz pública de auditoría; no importa modelos internos de identidad. Las pruebas AST comprueban estos límites.

OpenAPI exportado es la fuente de tipos HTTP. `projectView` adapta la respuesta a la representación visual, sin inventar registros ni datasets. El ejemplo no se inserta en la base y no cuenta como proyecto del usuario. Sidebar y acceso rápido consultan hasta 100 proyectos; la tabla tiene búsqueda/paginación real. Organizaciones, miembros y roles compartidos quedan pendientes.

En el frontend, TanStack Query maneja sesión y recursos remotos. Las mutaciones invalidan listados y actualizan el detalle. El cierre de sesión borra la caché. El proxy Next sólo transmite solicitudes, cookies y respuestas, limita cuerpos JSON a 64 KiB y tiene timeout; no contiene reglas de negocio ni acepta una URL de destino enviada por el cliente.

Pruebas backend en PostgreSQL con esquema efímero y rollback. E2E en base `_e2e` separada, con API y frontend propios; cubren cuentas, creación, persistencia sin localStorage, edición, archivo, cambio de cuenta y rechazo de acceso ajeno, además del recorrido analítico de demostración.

Próximo incremento: almacenamiento de objetos, ingesta CSV, versiones inmutables y diagnóstico real con trabajos controlados. Los nombres de archivo actuales son sólo metadatos: no existe aún almacenamiento de datasets.
