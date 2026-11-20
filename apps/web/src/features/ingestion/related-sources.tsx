"use client";

import { CheckCircle2, CircleSlash, Link2 } from "lucide-react";
import type { components } from "@dataflow/api-client";
import type { DatasetVersion } from "./api";
import { ROLE_LABELS, SchemaDiagram } from "./schema-diagram";

type RelatedTable = components["schemas"]["RelatedTable"];
type TableRelation = components["schemas"]["TableRelation"];
type RelatedView = components["schemas"]["RelatedView"];

/** Fase 31: modelo de datos de un conjunto relacionado (archivos o base de datos): el diagrama
 * del esquema, el papel de cada tabla, las vistas que se analizan y cada relación con su motivo. */
export function DataModelView({
  tables,
  relations,
  views,
  main,
  current,
}: {
  tables: RelatedTable[];
  relations: TableRelation[];
  views: RelatedView[];
  main?: string | null;
  current?: string;
}) {
  return (
    <>
      <SchemaDiagram tables={tables} relations={relations} />
      {views.length > 0 && (
        <ul className="view-list" aria-label="Vistas que se analizan">
          {views.map((view) => (
            <li
              key={view.name}
              className={view.name === current ? "current" : undefined}
            >
              <strong>
                {view.name}
                {view.name === main && " · se abre primero"}
                {view.name === current && " · esta versión"}
              </strong>
              <span>
                {view.kind === "entity" ? "Vista general" : "Vista de hechos"} ·{" "}
                {view.rows} registros · {view.columns} columnas
              </span>
              <small>{view.description}</small>
            </li>
          ))}
        </ul>
      )}
      <table className="related-table">
        <caption className="sr-only">Tablas del esquema</caption>
        <thead>
          <tr>
            <th scope="col">Tabla</th>
            <th scope="col">Papel</th>
            <th scope="col">Registros</th>
            <th scope="col">Columnas</th>
            <th scope="col">Motivo</th>
          </tr>
        </thead>
        <tbody>
          {tables.map((table) => (
            <tr key={table.label}>
              <th scope="row">{table.label}</th>
              <td>
                <span className={`role-chip ${table.role}`}>
                  {ROLE_LABELS[table.role]}
                </span>
              </td>
              <td>{table.rows}</td>
              <td>{table.columns}</td>
              <td>{table.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {relations.length > 0 && (
        <ul className="relation-list" aria-label="Relaciones encontradas">
          {relations.map((relation) => (
            <li
              key={`${relation.table}.${relation.column}>${relation.references_table}.${relation.references_column}`}
              className={relation.status}
            >
              {relation.status === "joined" ? (
                <CheckCircle2 size={15} aria-label="Usada" />
              ) : (
                <CircleSlash size={15} aria-label="No usada" />
              )}
              <span>
                <strong>
                  {relation.table}.{relation.column} →{" "}
                  {relation.references_table}.{relation.references_column}
                </strong>{" "}
                <small>
                  ({relation.cardinality ?? "N:1"},{" "}
                  {relation.origin === "declared"
                    ? "clave foránea de la base"
                    : "detectada por el nombre y los valores"}
                  )
                </small>
                <br />
                {relation.reason}
                {(relation.added_columns ?? []).length > 0 &&
                  ` Columnas añadidas: ${(relation.added_columns ?? []).join(", ")}.`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Fase 31: el modelo de datos del conjunto al que pertenece esta versión. */
export function RelatedSources({ version }: { version: DatasetVersion }) {
  const origin = version.source_origin;
  const tables = origin?.tables ?? [];
  if (!origin || tables.length === 0) return null;
  const views = origin.views ?? [];
  const title = !origin.joined
    ? "Esta tabla forma parte de un esquema de tablas relacionadas"
    : origin.view_kind === "entity"
      ? "Vista general de todas las tablas relacionadas"
      : "Vista de una tabla de hechos con las tablas a las que apunta";
  return (
    <section className="related-sources" aria-label="Tablas relacionadas">
      <header>
        <Link2 size={16} aria-hidden />
        <div>
          <h3>{title}</h3>
          <p>
            Regla {origin.rule}: las tablas se relacionan por columnas
            identificadoras cuyos valores existen en la otra tabla. Cada tabla y
            cada vista se analiza como su propia versión; las vistas de hechos
            no cambian sus registros y la vista general resume cada tabla de
            hechos por entidad.
          </p>
        </div>
      </header>
      <DataModelView
        tables={tables}
        relations={origin.relations ?? []}
        views={views}
        current={origin.joined ? origin.table : undefined}
      />
    </section>
  );
}
