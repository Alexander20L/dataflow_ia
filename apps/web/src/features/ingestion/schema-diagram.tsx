"use client";

import type { components } from "@dataflow/api-client";

type RelatedTable = components["schemas"]["RelatedTable"];
type TableRelation = components["schemas"]["TableRelation"];

const WIDTH = 220;
const GAP_X = 90;
const GAP_Y = 26;
const HEADER = 30;
const ROW = 18;
const MAX_ROWS = 10;
const PAD = 16;

export const ROLE_LABELS = {
  fact: "Tabla de hechos",
  entity: "Entidad principal",
  dimension: "Describe a otra",
  separate: "Por separado",
} as const;

type Box = {
  table: RelatedTable;
  x: number;
  y: number;
  height: number;
  shown: string[];
};

/** Columnas por niveles: las tablas de hechos a la izquierda y, a su derecha, las tablas a las
 * que apuntan (cada nivel, un paso más). Las tablas sin relaciones van en la última columna. */
function layout(tables: RelatedTable[], relations: TableRelation[]) {
  const usable = relations.filter(
    (r) => r.status === "joined" || !r.reason.includes("no están en"),
  );
  const level = new Map<string, number>();
  const pointed = new Set(usable.map((r) => r.references_table));
  for (const table of tables)
    if (
      !pointed.has(table.label) &&
      usable.some((r) => r.table === table.label)
    )
      level.set(table.label, 0);
  for (let step = 0; step < tables.length; step++)
    for (const relation of usable) {
      const from = level.get(relation.table);
      if (from === undefined) continue;
      const current = level.get(relation.references_table);
      if (current === undefined || current < from + 1)
        level.set(relation.references_table, Math.min(from + 1, tables.length));
    }
  const last = Math.max(0, ...level.values()) + 1;
  for (const table of tables)
    if (!level.has(table.label)) level.set(table.label, level.size ? last : 0);
  const columns = new Map<number, RelatedTable[]>();
  for (const table of tables) {
    const at = level.get(table.label) ?? 0;
    columns.set(at, [...(columns.get(at) ?? []), table]);
  }
  const boxes = new Map<string, Box>();
  let height = 0;
  const levels = [...columns.keys()].sort((a, b) => a - b);
  levels.forEach((at, index) => {
    let y = PAD;
    for (const table of columns.get(at) ?? []) {
      const headers = table.headers ?? [];
      const shown = headers.slice(0, MAX_ROWS);
      const boxHeight =
        HEADER + shown.length * ROW + (headers.length > MAX_ROWS ? ROW : 0) + 8;
      boxes.set(table.label, {
        table,
        x: PAD + index * (WIDTH + GAP_X),
        y,
        height: boxHeight,
        shown,
      });
      y += boxHeight + GAP_Y;
    }
    height = Math.max(height, y);
  });
  return {
    boxes,
    width: PAD * 2 + levels.length * WIDTH + (levels.length - 1) * GAP_X,
    height: height + PAD - GAP_Y,
  };
}

function rowY(box: Box, column: string) {
  const index = box.shown.indexOf(column);
  return box.y + HEADER + (index < 0 ? 0 : index) * ROW + ROW / 2 + 2;
}

/** Fase 31: «foto» del esquema: cada tabla con sus columnas (PK: clave; FK: apunta a otra) y
 * las relaciones entre tablas (línea continua: se usó en las vistas; discontinua: no). */
export function SchemaDiagram({
  tables,
  relations,
}: {
  tables: RelatedTable[];
  relations: TableRelation[];
}) {
  if (!tables.length) return null;
  const { boxes, width, height } = layout(tables, relations);
  const pointing = new Map<string, Set<string>>();
  for (const relation of relations)
    if (relation.status === "joined")
      pointing.set(
        relation.table,
        (pointing.get(relation.table) ?? new Set()).add(relation.column),
      );
  const joined = relations.filter((r) => r.status === "joined").length;
  return (
    <figure className="schema-diagram">
      <div className="schema-scroll">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          role="img"
          aria-label={`Diagrama del esquema: ${tables.length} tablas y ${joined} relaciones usadas.`}
        >
          {relations.map((relation) => {
            const from = boxes.get(relation.table);
            const to = boxes.get(relation.references_table);
            if (!from || !to) return null;
            const forward = to.x >= from.x;
            const x1 = forward ? from.x + WIDTH : from.x;
            const x2 = forward ? to.x : to.x + WIDTH;
            const y1 = rowY(from, relation.column);
            const y2 = rowY(to, relation.references_column);
            const bend =
              Math.max(40, Math.abs(x2 - x1) / 2) * (forward ? 1 : -1);
            const used = relation.status === "joined";
            return (
              <g
                key={`${relation.table}.${relation.column}>${relation.references_table}.${relation.references_column}`}
                className={used ? "edge used" : "edge unused"}
              >
                <path
                  d={`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`}
                  fill="none"
                  markerEnd="url(#schema-arrow)"
                />
                <text
                  x={(x1 + x2) / 2}
                  y={(y1 + y2) / 2 - 4}
                  textAnchor="middle"
                >
                  {relation.cardinality ?? "N:1"}
                </text>
              </g>
            );
          })}
          <defs>
            <marker
              id="schema-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
            </marker>
          </defs>
          {[...boxes.values()].map((box) => {
            const keys = new Set(box.table.keys ?? []);
            const fks = pointing.get(box.table.label) ?? new Set<string>();
            const hidden = (box.table.headers ?? []).length - box.shown.length;
            return (
              <g
                key={box.table.label}
                className={`table-box ${box.table.role}`}
              >
                <rect
                  x={box.x}
                  y={box.y}
                  width={WIDTH}
                  height={box.height}
                  rx={8}
                />
                <rect
                  className="table-head"
                  x={box.x}
                  y={box.y}
                  width={WIDTH}
                  height={HEADER - 6}
                  rx={8}
                />
                <text className="table-name" x={box.x + 10} y={box.y + 16}>
                  {box.table.label.length > 26
                    ? `${box.table.label.slice(0, 25)}…`
                    : box.table.label}
                </text>
                <text
                  className="table-role"
                  x={box.x + WIDTH - 10}
                  y={box.y + 16}
                  textAnchor="end"
                >
                  {box.table.rows} reg.
                </text>
                {box.shown.map((column, index) => (
                  <g key={column}>
                    <text
                      className={keys.has(column) ? "column key" : "column"}
                      x={box.x + 10}
                      y={box.y + HEADER + index * ROW + ROW / 2 + 6}
                    >
                      {column.length > 24 ? `${column.slice(0, 23)}…` : column}
                    </text>
                    {(keys.has(column) || fks.has(column)) && (
                      <text
                        className="column-tag"
                        x={box.x + WIDTH - 10}
                        y={box.y + HEADER + index * ROW + ROW / 2 + 6}
                        textAnchor="end"
                      >
                        {[
                          keys.has(column) ? "PK" : "",
                          fks.has(column) ? "FK" : "",
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </text>
                    )}
                  </g>
                ))}
                {hidden > 0 && (
                  <text
                    className="column more"
                    x={box.x + 10}
                    y={box.y + HEADER + box.shown.length * ROW + ROW / 2 + 6}
                  >
                    +{hidden} columnas más
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption>
        <span className="legend used">Relación usada en las vistas</span>
        <span className="legend unused">Relación encontrada, no usada</span>
        <span>PK: clave · FK: apunta a otra tabla</span>
      </figcaption>
    </figure>
  );
}
