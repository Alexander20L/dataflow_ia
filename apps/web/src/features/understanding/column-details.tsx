"use client";
import { useState } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import type { EditorDraft } from "./api";

type EditorColumn = EditorDraft["columns"][number];
export function ColumnDetails({
  name,
  column,
  onClose,
  onApply,
}: {
  name: string;
  column: EditorColumn;
  onClose: () => void;
  onApply: (column: EditorColumn) => void;
}) {
  const [value, setValue] = useState(column);
  const [tokens, setTokens] = useState(
    JSON.stringify(column.null_policy.tokens),
  );
  const [error, setError] = useState("");
  return (
    <Dialog title={`Definición de ${name}`} onClose={onClose}>
      <form
        className="semantic-detail-form"
        onSubmit={(e) => {
          e.preventDefault();
          try {
            const parsed =
              value.null_policy.mode === "explicit_tokens"
                ? z.array(z.string().max(100)).max(20).parse(JSON.parse(tokens))
                : [];
            onApply({
              ...value,
              null_policy: {
                mode: value.null_policy.mode,
                tokens:
                  value.null_policy.mode === "explicit_tokens" ? parsed : [],
              },
            });
          } catch {
            setError(
              'Escribe un array JSON de hasta 20 cadenas. Ejemplo: ["NA", ""].',
            );
          }
        }}
      >
        <label htmlFor="semantic-description">Descripción</label>
        <textarea
          id="semantic-description"
          maxLength={1000}
          rows={3}
          value={value.description ?? ""}
          onChange={(e) =>
            setValue((v) => ({ ...v, description: e.target.value || null }))
          }
        />
        <label htmlFor="semantic-unit">Unidad</label>
        <input
          id="semantic-unit"
          maxLength={80}
          placeholder="kg, unidades, porcentaje…"
          value={value.unit ?? ""}
          onChange={(e) =>
            setValue((v) => ({ ...v, unit: e.target.value || null }))
          }
          disabled={value.role !== "measure"}
        />
        <label htmlFor="semantic-currency">Moneda ISO 4217</label>
        <input
          id="semantic-currency"
          maxLength={3}
          placeholder="Sin definir"
          value={value.currency ?? ""}
          onChange={(e) =>
            setValue((v) => ({
              ...v,
              currency: e.target.value.toUpperCase() || null,
            }))
          }
          disabled={value.role !== "measure"}
        />
        <label htmlFor="semantic-format">Formato de interpretación</label>
        <select
          id="semantic-format"
          value={value.parse_format ?? ""}
          onChange={(e) =>
            setValue((v) => ({
              ...v,
              parse_format: (e.target.value ||
                null) as EditorColumn["parse_format"],
            }))
          }
        >
          <option value="">Sin declarar</option>
          <option value="integer_ascii">Entero ASCII</option>
          <option value="decimal_dot">Decimal con punto</option>
          <option value="iso_date">Fecha ISO YYYY-MM-DD</option>
          <option value="boolean_lowercase">true / false exactos</option>
        </select>
        <label htmlFor="semantic-nulls">Política declarada de nulos</label>
        <select
          id="semantic-nulls"
          value={value.null_policy.mode}
          onChange={(e) =>
            setValue((v) => ({
              ...v,
              null_policy: {
                ...v.null_policy,
                mode: e.target.value as EditorColumn["null_policy"]["mode"],
              },
            }))
          }
        >
          <option value="preserve">Conservar interpretación actual</option>
          <option value="empty_is_null">Vacío representa nulo</option>
          <option value="explicit_tokens">Tokens explícitos</option>
        </select>
        {value.null_policy.mode === "explicit_tokens" && (
          <>
            <label htmlFor="semantic-tokens">Tokens nulos (array JSON)</label>
            <textarea
              id="semantic-tokens"
              rows={3}
              value={tokens}
              onChange={(e) => setTokens(e.target.value)}
            />
            <small className="muted">
              Las cadenas vacías y los espacios se conservan literalmente.
            </small>
          </>
        )}
        <div className="info-banner">
          <span>
            Esto declara significado y formato. No convierte valores, no aplica
            tokens y no limpia datos.
          </span>
        </div>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <div className="form-footer">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit">Aplicar al borrador</Button>
        </div>
      </form>
    </Dialog>
  );
}
