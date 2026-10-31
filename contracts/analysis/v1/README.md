# Contratos de diseño de análisis v1

**Especificación objetivo de Fase 1, no contrato HTTP implementado.** Ver `docs/architecture/phase-1/README.md` para entidades, invariantes, estados y migración.

## Archivos

- `schema.mjs`: fuente del JSON Schema 2020-12. Sus `$defs` describen entidades; el documento raíz es sólo un contenedor de escenarios de prueba.
- `schema.json`: esquema generado, apto para inspección/validadores estándar.
- `fixtures.mjs`: escenario sintético determinista, sin reloj actual ni UUID aleatorios.
- `examples.json`: escenario generado con hashes de contenido reales para revisiones/configuración/entorno/efecto/tablas lógicas.
- `canonical.mjs`: algoritmo canónico restringido de referencia, con dominios de hash separados.
- `verify.mjs`: chequeo estructural y un subconjunto explícito de invariantes cruzadas, más casos negativos.

## Uso desde la raíz

```sh
npm install
npm run contracts:examples
npm run contracts:check
```

`contracts:examples` genera **schema.json y examples.json**; ambos se editan a través de sus fuentes. `contracts:check` no modifica archivos, abre la base ni llama a la API. Ajv/Ajv-formats son dependencias de desarrollo para validar JSON Schema y formatos UUID/UTC; no se integran al motor de producción.

## Escenario

1. Registrar un original CSV con 3 filas y 2 columnas.
2. Extraer tabla, perfil y calidad con una ejecución de ingesta.
3. Guardar una semántica pendiente y otra confirmada por el usuario ficticio.
4. Ejecutar otro diagnóstico de calidad sobre la **misma versión y representación**.
5. Calcular preview de trim que cambia un campo de espacios a null.
6. Aprobar el efecto exacto.
7. Fallar un intento de apply y publicar sólo desde el siguiente.
8. Publicar una versión derivada con correspondencia de filas y calidad asociada.
9. Vincular una evidencia al resultado de calidad derivado.

Los blobs Parquet y las huellas de código/entorno son **referencias simbólicas**, no archivos binarios ni fingerprints del despliegue actual. Las filas de fixture permiten verificar hashes lógicos; el CSV incluido en `source_fixtures` sí verifica su hash físico. Esto no prueba lectura de Parquet, extracción, estadísticas, permisos reales, revocación transaccional ni concurrencia: esas garantías requieren las pruebas de implementación de las fases siguientes. Los ejemplos no contienen información de usuarios.

## Evolución

Los schemas no se importan desde las aplicaciones ni generan tipos HTTP paralelos. Durante Fase 2 los modelos implementados deberán producir/aceptar escenarios compatibles y FastAPI seguirá generando OpenAPI. Una modificación incompatible de estas invariantes requiere revisar el diseño y versionar el contrato; no basta con cambiar un fixture para que pase el chequeo.
