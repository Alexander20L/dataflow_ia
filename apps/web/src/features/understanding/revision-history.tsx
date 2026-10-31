"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import {
  roles,
  reviews,
  useSemanticHistory,
  useSemanticRevision,
  type SemanticRevision,
} from "./api";

export function RevisionHistory({
  artifactId,
  head,
  onClose,
}: {
  artifactId: string;
  head: SemanticRevision | null;
  onClose: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const list = useSemanticHistory(artifactId, offset);
  const [selected, setSelected] = useState<string | null>(head?.id ?? null);
  const detail = useSemanticRevision(selected);
  const revision = detail.data;
  const differences: string[] = [];
  if (revision && head && revision.id !== head.id) {
    if (
      revision.content.dataset_description !== head.content.dataset_description
    )
      differences.push("Descripción del dataset");
    if (
      JSON.stringify(revision.content.row_grain) !==
      JSON.stringify(head.content.row_grain)
    )
      differences.push("Significado de cada fila / revisión");
    if (
      JSON.stringify(revision.content.key) !== JSON.stringify(head.content.key)
    )
      differences.push("Clave / política de nulos / revisión");
    for (const column of revision.content.columns) {
      const current = head.content.columns.find((c) => c.id === column.id);
      if (JSON.stringify(column) !== JSON.stringify(current))
        differences.push(`Definición o revisión de ${column.name}`);
    }
  }
  return (
    <Dialog title="Historial semántico" onClose={onClose}>
      <div className="semantic-history">
        <label htmlFor="semantic-history-revision">Revisión guardada</label>
        <select
          id="semantic-history-revision"
          value={selected ?? ""}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Elige una revisión</option>
          {list.data?.items.map((item) => (
            <option key={item.id} value={item.id}>
              Revisión {item.revision}
              {item.id === head?.id ? " · actual" : ""}
            </option>
          ))}
          {!list.data?.items.length && <option value="">Sin revisiones</option>}
        </select>
        {list.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(list.error)}
          </p>
        )}
        <div className="pagination">
          <Button
            variant="ghost"
            size="sm"
            disabled={!offset}
            onClick={() => {
              setOffset((o) => o - 20);
              setSelected(null);
            }}
          >
            Más recientes
          </Button>
          <span>{list.data?.total ?? 0} revisiones</span>
          <Button
            variant="ghost"
            size="sm"
            disabled={offset + 20 >= (list.data?.total ?? 0)}
            onClick={() => {
              setOffset((o) => o + 20);
              setSelected(null);
            }}
          >
            Anteriores
          </Button>
        </div>
        {detail.isPending && selected && (
          <p role="status">Cargando revisión…</p>
        )}
        {detail.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(detail.error)}
          </p>
        )}
        {revision && (
          <>
            <p className="eyebrow">
              REVISIÓN {revision.revision} · SÓLO LECTURA
            </p>
            <p className="fine-print">
              Guardada {new Date(revision.created_at).toLocaleString("es-ES")} ·
              actor <span className="mono">{revision.created_by}</span>
            </p>
            <p className="mono semantic-hash">
              SHA-256 {revision.content_sha256}
            </p>
            <h3>Dataset</h3>
            <p>{revision.content.dataset_description || "Sin descripción"}</p>
            <h3>Cada fila representa</h3>
            <p>
              {revision.content.row_grain.description || "Pendiente"} ·{" "}
              {reviews[revision.content.row_grain.review.state]}
            </p>
            <h3>Columnas</h3>
            <div className="semantic-history-columns">
              {revision.content.columns.map((c) => (
                <div key={c.id}>
                  <strong>{c.name}</strong>
                  <span>
                    {roles[c.role]} · {reviews[c.review.state]}
                  </span>
                  <small>
                    {c.currency ?? c.unit ?? "Unidad/moneda no definida"}
                  </small>
                  <p>{c.description}</p>
                  <small>
                    Origen: {c.review.origin}{" "}
                    {c.review.reviewed_at
                      ? `· ${new Date(c.review.reviewed_at).toLocaleString("es-ES")}`
                      : ""}
                  </small>
                </div>
              ))}
            </div>
            {revision.id !== head?.id && (
              <div className="info-banner">
                <span>
                  <strong>Diferencias respecto a la revisión actual:</strong>
                  <br />
                  {differences.length
                    ? differences.join("; ")
                    : "Mismas definiciones registradas."}
                </span>
              </div>
            )}
            <p className="fine-print muted">
              Consultar una revisión anterior no cambia la actual ni las
              ejecuciones que la utilizaron.
            </p>
          </>
        )}
      </div>
    </Dialog>
  );
}
