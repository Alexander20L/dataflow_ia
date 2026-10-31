import { writeFile } from "node:fs/promises";
import { buildExamples } from "./fixtures.mjs";
import { schema } from "./schema.mjs";

for (const [name, value] of [
  ["schema.json", schema],
  ["examples.json", buildExamples()],
]) {
  await writeFile(
    new URL(name, import.meta.url),
    JSON.stringify(value, null, 2) + "\n",
  );
  console.log(`Generado: contracts/analysis/v1/${name}`);
}
