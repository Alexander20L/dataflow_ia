# Anexo E — Datasets y acceso

DataFlow AI no se entrena con un dataset: analiza los datos que sube cada usuario. Todos los conjuntos
usados en la evaluación son **sintéticos**, están en el repositorio o se generan con semilla fija, y no
contienen datos personales reales.

| Conjunto                                            | Ruta                                                                     | Uso en el TDDR                                                          |
| --------------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Tablas académicas relacionadas                      | `examples/relacionadas/` (5 CSV)                                         | Recorrido completo de archivos relacionados (§5.4.2), capturas (§3.3.6) |
| Ventas con problemas de calidad                     | `examples/ventas_calidad.csv`                                            | Recorrido completo de un CSV pequeño (§5.4.2)                           |
| Libro de ventas                                     | `examples/ventas.xlsx`                                                   | Ejemplo de Excel (no usado en las mediciones)                           |
| Esquemas con verdad de referencia                   | generados por `docs/tddr/bench/relations_benchmark.py` (semilla 2026)    | Exactitud de `relations-v1` (§5.4.1)                                    |
| Pedidos sintéticos de 1.000 / 10.000 / 50.000 filas | generados por `docs/tddr/bench/api_benchmark.py` (semilla = nº de filas) | Escalabilidad (§5.4.3)                                                  |
| Dataset de aceptación de ventas                     | `apps/api/tests/reference_sales.py`                                      | Pruebas automáticas                                                     |

## E.1 `examples/relacionadas/` — descripción y estadísticas

Modelo: `carreras` ← `estudiantes` ← (`asistencia`, `notas`) → `cursos` → `carreras`. 7.830 registros en
total, sin valores faltantes. Estadísticas calculadas con Polars sobre los archivos completos
(media, desviación típica muestral, mínimo, mediana y máximo para las numéricas; los tres valores más
frecuentes para el texto).

**asistencia.csv** (6.000 × 6)

| Columna            | Tipo            | Faltantes | Distintos | Media | Desv. | Mín | Mediana | Máx / más frecuentes                  |
| ------------------ | --------------- | --------- | --------- | ----- | ----- | --- | ------- | ------------------------------------- |
| asistencia_id      | texto (clave)   | 0         | 6.000     | —     | —     | —   | —       | único por fila                        |
| estudiante_id      | texto (FK)      | 0         | 300       | —     | —     | —   | —       | 20 registros por estudiante           |
| curso_id           | texto (FK)      | 0         | 25        | —     | —     | —   | —       | K001 (348), K002 (348), K003 (348)    |
| mes                | texto (periodo) | 0         | 4         | —     | —     | —   | —       | 1.500 por mes (4 meses desde 2025-04) |
| clases_programadas | numérica        | 0         | 3         | 8,765 | 0,831 | 8   | 9       | 10                                    |
| clases_asistidas   | numérica        | 0         | 7         | 6,993 | 1,228 | 4   | 7       | 10                                    |

**notas.csv** (1.500 × 6)

| Columna       | Tipo               | Faltantes | Distintos | Media  | Desv. | Mín | Mediana | Máx / más frecuentes            |
| ------------- | ------------------ | --------- | --------- | ------ | ----- | --- | ------- | ------------------------------- |
| nota_id       | texto (clave)      | 0         | 1.500     | —      | —     | —   | —       | único por fila                  |
| estudiante_id | texto (FK)         | 0         | 300       | —      | —     | —   | —       | 5 por estudiante                |
| curso_id      | texto (FK)         | 0         | 25        | —      | —     | —   | —       | K001 (87), K002 (87), K003 (87) |
| periodo       | texto              | 0         | 1         | —      | —     | —   | —       | 2025-1 (1.500)                  |
| nota          | numérica           | 0         | 109       | 15,840 | 2,374 | 7,5 | 15,9    | 20,0                            |
| aprobado      | texto (dicotómica) | 0         | 2         | —      | —     | —   | —       | Sí (1.480), No (20)             |

**estudiantes.csv** (300 × 8)

| Columna       | Tipo               | Faltantes | Distintos | Media  | Desv. | Mín | Mediana | Máx / más frecuentes         |
| ------------- | ------------------ | --------- | --------- | ------ | ----- | --- | ------- | ---------------------------- |
| estudiante_id | texto (clave)      | 0         | 300       | —      | —     | —   | —       | único                        |
| carrera_id    | texto (FK)         | 0         | 5         | —      | —     | —   | —       | C01 (87), C02 (72), C04 (52) |
| fecha_ingreso | fecha ISO (texto)  | 0         | 268       | —      | —     | —   | —       | —                            |
| sexo          | texto (dicotómica) | 0         | 2         | —      | —     | —   | —       | M (157), F (143)             |
| edad          | numérica           | 0         | 14        | 23,500 | 4,166 | 17  | 24      | 30                           |
| beca          | texto (dicotómica) | 0         | 2         | —      | —     | —   | —       | No (216), Sí (84)            |
| trabaja       | texto (dicotómica) | 0         | 2         | —      | —     | —   | —       | No (189), Sí (111)           |
| activo        | texto (dicotómica) | 0         | 2         | —      | —     | —   | —       | Sí (267), No (33)            |

**cursos.csv** (25 × 4): `curso_id` (clave), `curso` (21 distintos), `carrera_id` (FK, 5 cursos por
carrera), `creditos` (media 3,880, desv. 0,781, 3–5).

**carreras.csv** (5 × 4): `carrera_id` (clave), `carrera`, `facultad` (4 distintas), `costo_semestre`
(media 3.740, desv. 350,714, 3.300–4.200).

## E.2 Esquemas sintéticos del benchmark de relaciones

`relations_benchmark.py` genera 200 esquemas (semilla 2026). Cada uno tiene una tabla de dimensión
(4–12 registros), una entidad principal (30–150) a la que la dimensión describe, opcionalmente una segunda
entidad (20–80) y de 1 a 3 tablas de hechos (80–400 registros) con columnas `id`, `fecha`, `cantidad`
(1–10) y `monto`. Las claves de las tablas usan convenciones variadas (`id`, `codigo`, `id_<tabla>`,
`<Tabla>ID`) y empiezan en 1, 100 o 1000. Las claves foráneas se nombran por convención (`id_cliente`,
`cliente_id`, `IdCliente`, `codigo_cliente`…), con el mismo nombre que la clave o, en un 12 % de los
casos, con un nombre libre (`comprador`, `titular`…); en un 10 % se introduce un valor sin pareja
(huérfano). La verdad de referencia son las claves foráneas intencionales: 718 relaciones.

## E.3 Acceso

Repositorio: <https://github.com/Alexander20L/dataflow_ia> (privado; acceso a solicitud de los autores o
del docente). Los generadores de datos y los resultados en JSON están en `docs/tddr/bench/`.
