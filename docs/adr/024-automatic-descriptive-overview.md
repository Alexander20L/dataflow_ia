# ADR-024 — Dashboard descriptivo sin configuración al importar

Estado: implementado para el incremento B1. Referencia: [analista automático](../architecture/automatic-analyst.md).

## Contexto

El recorrido por políticas y mapeos exige decisiones antes de obtener un dashboard. El nuevo objetivo de producto es mostrar resultados útiles al cargar una fuente sin pedir configuración. No podemos confirmar automáticamente significado de negocio ni autorizar limpieza destructiva usando sólo nombres o tipos sugeridos.

## Decisión

- Añadir `understanding.profile@2` en `analysis-v9`, conservando `@1` y las referencias históricas.
- Incluir un snapshot descriptivo opcional `overview` en el perfil publicado de las nuevas importaciones, tanto CSV como XLSX. El worker lo calcula en el mismo subproceso acotado; la publicación sigue siendo atómica y protegida por fencing.
- Mostrarlo directamente, sin políticas, mapeos ni IA. La consulta HTTP sólo recupera JSON almacenado y la interfaz no agrega ni transforma cifras.
- Usar etiquetas neutrales: conteos, completitud, duplicados adicionales, promedio/mínimo/máximo y frecuencias. No inferir ingresos, moneda, ventas, stock actual ni sumas aditivas.
- Mantener la fuente, sus ceros iniciales, espacios, nulos y duplicados. Interpretaciones numéricas ambiguas no se fuerzan.
- Acotar tarjetas, gráficos, categorías y detalle, y registrar exclusiones o truncamientos. Tratar nombres y categorías como texto, nunca HTML.
- No cambiar planes, artefactos ni dashboards publicados. No migrar ni recalcular silenciosamente las cargas históricas. Sus vistas técnicas existentes siguen accesibles.

## Consecuencias

Se obtiene un primer resultado sin ampliar el número de trabajos ni exigir un servicio adicional. No es un dashboard editable del módulo `dashboards`, ni la interpretación automática de negocio, ni la auditoría textual. Esas capacidades se integrarán en incrementos posteriores. El selector manual de hoja de Excel y las herramientas avanzadas permanecen por compatibilidad hasta completar el descubrimiento automático y la nueva interfaz.

La serialización de los artefactos `profile@1` omite el campo nuevo; los planes importados con catálogos anteriores siguen publicando exactamente su resultado previo. La API expone `overview: null` para perfiles sin snapshot.
