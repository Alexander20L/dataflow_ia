"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useRecords, type Inspection } from "./api";
import { formatNumber } from "./labels";

const SIZES = [25, 50, 100];

/** Registros tal como se leyeron, paginados, ordenados y buscados en el servidor. `focusRow`
 * (Fase 23): fila que se quiere ver desde Calidad; se abre su página y se resalta. */
export function RecordsView({
  versionId,
  inspection,
  focusRow,
}: {
  versionId: string;
  inspection: Inspection;
  focusRow?: number;
}) {
  const [size, setSize] = useState(25);
  const [page, setPage] = useState(
    focusRow ? Math.floor((focusRow - 1) / 25) : 0,
  );
  const [sort, setSort] = useState<string | undefined>();
  const [descending, setDescending] = useState(false);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState<string | undefined>();
  const records = useRecords(versionId, {
    page,
    size,
    sort,
    descending,
    search,
  });
  const columns = inspection.columns;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSearch(draft.trim() || undefined);
    setPage(0);
  };
  const toggle = (id: string) => {
    if (sort !== id) {
      setSort(id);
      setDescending(false);
    } else if (!descending) setDescending(true);
    else {
      setSort(undefined);
      setDescending(false);
    }
    setPage(0);
  };
  const jump = (id: string) =>
    document
      .getElementById(`records-col-${id}`)
      ?.scrollIntoView({ inline: "center", block: "nearest" });
  const data = records.data;
  const focusVisible =
    focusRow != null &&
    !sort &&
    !search &&
    data?.rows.some((row) => row.row_number === focusRow);
  useEffect(() => {
    if (focusVisible)
      document
        .getElementById(`records-row-${focusRow}`)
        ?.scrollIntoView({ block: "center" });
  }, [focusVisible, focusRow]);
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="dataset-records">
      <div className="table-toolbar">
        <form role="search" onSubmit={submit} className="records-search">
          <label htmlFor="records-search" className="sr-only">
            Buscar en los registros
          </label>
          <input
            id="records-search"
            type="search"
            maxLength={100}
            placeholder="Buscar un valor en todas las columnas"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" size="sm" variant="outline">
            <Search size={14} aria-hidden /> Buscar
          </Button>
        </form>
        <label className="records-jump">
          Ir a la columna
          <select
            defaultValue=""
            onChange={(event) => jump(event.target.value)}
          >
            <option value="" disabled>
              Elegir…
            </option>
            {columns.map((column) => (
              <option key={column.id} value={column.id}>
                {column.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {records.isError ? (
        <div className="empty-state">
          <p role="alert">{errorMessage(records.error)}</p>
          <Button onClick={() => void records.refetch()}>Reintentar</Button>
        </div>
      ) : !data ? (
        <p className="empty-copy" role="status">
          Cargando registros…
        </p>
      ) : (
        <>
          <p className="muted" role="status">
            {search
              ? `${formatNumber(total)} registros contienen «${search}».`
              : `${formatNumber(total)} registros.`}{" "}
            Los valores se muestran tal como se leyeron; las celdas sin valor
            aparecen como <span className="null-cell">nulo</span>.
          </p>
          <div className="table-scroll" tabIndex={0} aria-label="Registros">
            <table className="data-table records-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  {columns.map((column) => {
                    const active = sort === column.id;
                    return (
                      <th
                        key={column.id}
                        id={`records-col-${column.id}`}
                        scope="col"
                        aria-sort={
                          active
                            ? descending
                              ? "descending"
                              : "ascending"
                            : "none"
                        }
                      >
                        <button
                          type="button"
                          className="sort-button"
                          onClick={() => toggle(column.id)}
                          title={`Ordenar por ${column.name}`}
                        >
                          {column.name}
                          {active ? (
                            descending ? (
                              <ArrowDown size={12} aria-hidden />
                            ) : (
                              <ArrowUp size={12} aria-hidden />
                            )
                          ) : (
                            <ArrowUpDown size={12} aria-hidden />
                          )}
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {data.rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length + 1}>
                      Ningún registro coincide con la búsqueda.
                    </td>
                  </tr>
                ) : (
                  data.rows.map((row) => (
                    <tr
                      key={row.row_number}
                      id={`records-row-${row.row_number}`}
                      className={
                        focusVisible && row.row_number === focusRow
                          ? "focus-row"
                          : undefined
                      }
                      aria-current={
                        focusVisible && row.row_number === focusRow
                          ? "true"
                          : undefined
                      }
                    >
                      <th scope="row">{row.row_number}</th>
                      {data.columns.map((name) => {
                        const value = row.values[name];
                        return (
                          <td key={name}>
                            {value == null ? (
                              <span className="null-cell">nulo</span>
                            ) : value.trim() === "" ? (
                              <span
                                className="null-cell"
                                title="Texto en blanco"
                              >
                                «{value}»
                              </span>
                            ) : (
                              value
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>
              Página {page + 1} de {pages}
            </span>
            <label>
              Filas por página
              <select
                value={size}
                onChange={(event) => {
                  setSize(Number(event.target.value));
                  setPage(0);
                }}
              >
                {SIZES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <Button
              size="sm"
              variant="outline"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Anterior
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page + 1 >= pages}
              onClick={() => setPage(page + 1)}
            >
              Siguiente
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
