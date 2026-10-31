# ADR-009 — Identidad individual con sesiones opacas

Estado: aceptado para el primer incremento funcional.

## Contexto

No hay proveedor OIDC elegido ni requisitos de organizaciones/invitaciones. Se necesita verificar acceso real por propietario y persistencia sin exigir servicios externos al desarrollo local.

## Decisión

Registrar cuentas individuales con correo normalizado y contraseña Argon2id. Sesiones aleatorias de 384 bits en cookie HttpOnly, SameSite=Lax y Secure configurable (obligatorio con HTTPS). Guardar sólo hash SHA-256 del token de sesión en PostgreSQL; caducidad absoluta de 12 horas por defecto y revocación al cerrar sesión. CSRF por sesión más validación de Origin para mutaciones. Ningún token de autenticación en localStorage. Rate limit persistido de 15 intentos/correo y 100/IP por 15 minutos, serializado con bloqueos transaccionales PostgreSQL.

Next.js actúa únicamente como proxy same-origin de transporte con URL interna configurable en runtime. FastAPI siempre autoriza. Los secretos nunca son variables NEXT_PUBLIC. Caché remota borrada al cerrar sesión o cambiar de cuenta. Proyectos con propietario único, búsqueda/paginación en backend y revisión optimista para escrituras.

## Alternativas

- OIDC externo: apropiado cuando se elija proveedor; añade configuración y dependencia operativa ahora.
- JWT en localStorage: descartado por exposición y revocación más compleja.
- Sesiones sólo en memoria: descartadas por pérdida tras reinicio y falta de coordinación.

## Consecuencias y riesgos

La aplicación mantiene hashes y sesiones: se deben añadir recuperación de cuenta y verificación de correo antes de ofrecer autoservicio público. Registro deshabilitable por entorno. Sin roles colaborativos todavía; no se debe interpretar propietario único como RBAC completo. Las sesiones vencidas permanecen inertes hasta su futura limpieza programada. El limitador de IP ve la conexión del proxy; en producción necesita una política de proxy confiable o limitación en ingress. No se promete continuidad indefinida de sesión ni refresh automático. Identidad aislada mediante contratos públicos para permitir migración posterior a OIDC.
