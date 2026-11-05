"use client";
import { cell, type EffectSample } from "./api";

export function BeforeAfter({
  samples,
  names,
  total,
}: {
  samples: EffectSample[];
  names: Record<string, string>;
  total: number;
}) {
  if (!samples.length)
    return (
      <p className="empty-copy">
        Esta limpieza no modifica ni excluye registros.
      </p>
    );
  return (
    <div className="before-after">
      <p className="fine-print muted">
        Muestra de {samples.length} de {total} registro(s) afectados, en orden
        de origen. Los conteos se calculan sobre el dataset completo.
      </p>
      <div className="table-scroll bordered">
        <table aria-label="Ejemplos antes y después">
          <thead>
            <tr>
              <th>Registro</th>
              <th>Cambio</th>
              <th>Columna</th>
              <th>Antes</th>
              <th>Después</th>
            </tr>
          </thead>
          <tbody>
            {samples.flatMap((sample) =>
              sample.column_ids.map((id, index) => {
                const after =
                  sample.after === null || sample.after === undefined
                    ? undefined
                    : sample.after[id];
                const createdNull =
                  sample.change === "modified" &&
                  sample.before[id] !== null &&
                  after === null;
                return (
                  <tr
                    key={`${sample.source_row}-${id}`}
                    className={createdNull ? "created-null" : undefined}
                  >
                    <td>{index === 0 ? sample.source_row : ""}</td>
                    <td>
                      {index === 0 &&
                        (sample.change === "excluded" ? (
                          <span className="badge review">Excluido</span>
                        ) : (
                          <span className="badge neutral">Modificado</span>
                        ))}
                    </td>
                    <td>{names[id] ?? id}</td>
                    <td className="mono">{cell(sample.before[id])}</td>
                    <td className="mono">
                      {sample.change === "excluded" ? (
                        "—"
                      ) : (
                        <>
                          {cell(after)}
                          {createdNull && (
                            <span className="badge review">Nulo creado</span>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
