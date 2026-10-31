# Incrementos y aceptación

1. Arquitectura base y prototipo frontend (actual): shell, dashboard, proyectos/importación y nueve etapas con fixture coherente. Documentar capacidades parciales.
2. Completar prototipo: persistencia/resize del editor BI, comparador detallado de ejecuciones, revisión visual y accesibilidad con usuarios.
3. Backend base: FastAPI, PostgreSQL, Alembic, acceso por proyecto, OpenAPI y cliente generado. Autorización de cada recurso.
4. Ingesta CSV y calidad: objetos, hash, perfil, reglas y paginación real. Original intacto. Después XLSX y Parquet.
5. Trabajos confiables y limpieza: outbox, cola/worker, reintentos, aprobación ligada a hash, nueva versión y recuperación de fallos.
6. Analítica y BI: estadísticas, métricas versionadas y dashboards persistentes. Restricciones de expresiones y presupuestos de cómputo.
7. IA e informes: adaptadores, validación de evidencia, evaluación, exportación PDF del servidor y auditoría.
8. Operación: aislamiento, límites, restauración, alertas, pruebas de volumen y despliegue independiente. Conectores de BD tras estabilizar archivos.

## Verificación manual del primer incremento

- Inicio muestra 3 proyectos, 1 dataset y ninguna ejecución pendiente ficticia.
- Abrir nuevo análisis, validar nombre vacío y seleccionar ejemplo o archivo. Se advierte que el archivo no se procesa.
- Crear proyecto con archivo muestra preparación, no resultados atribuidos a ese archivo.
- Abrir ventas → calidad: 8 importes nulos de 240 filas.
- Limpieza → aprobar → confirmar: v2 contiene 232 filas. v1 sigue seleccionable.
- Cambiar de versión actualiza tabla, calidad y conteo. Totales excluyen nulos explícitamente.
- Filtrar región en análisis actualiza tarjetas y gráfico.
- Exportar CSV descarga datos sintéticos. PDF abre impresión de informe con contexto y limitaciones.
- Tema y proyectos sobreviven a recarga. Reset devuelve el estado inicial.
- Revisar móvil, foco de teclado, diálogo Escape, estados vacíos y ruta desconocida.

## Pendientes explícitos

Sin API, autenticación ni LLM. Archivos seleccionados no se analizan. La simulación sólo registra una limpieza del fixture y no representa un sistema de trabajos. No hay arrastre/redimensionamiento de tarjetas, persistencia de dashboards ni auditoría durable. Las sugerencias semánticas y respuestas del asistente son guionizadas. Los tipos frontend de demostración se reemplazarán por tipos generados donde correspondan al contrato HTTP.
