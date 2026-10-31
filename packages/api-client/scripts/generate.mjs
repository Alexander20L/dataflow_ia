import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";
import ts from "typescript";

const schema = JSON.parse(
  await readFile(
    new URL("../../../contracts/openapi/dataflow.json", import.meta.url),
    "utf8",
  ),
);
const ast = await openapiTS(schema, {
  transform(node) {
    if (node.format === "binary")
      return ts.factory.createTypeReferenceNode("Blob");
  },
});
await writeFile(
  new URL("../src/schema.ts", import.meta.url),
  "/** Autogenerado desde OpenAPI. No editar manualmente. */\n" +
    astToString(ast),
);
console.log(
  "Cliente actualizado desde el contrato OpenAPI (binarios tipados como Blob).",
);
