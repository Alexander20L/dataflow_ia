"use client";
import { useState } from "react";
import { Bot, LoaderCircle, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import {
  useAutomationPolicy,
  useSavePolicy,
  type CleaningOperation,
  type PolicyContent,
  type PolicyContentInput,
} from "./api";

const OPERATIONS: { id: CleaningOperation; label: string }[] = [
  { id: "cleaning.normalize_null_tokens", label: "Marcadores de nulo" },
  { id: "cleaning.trim_whitespace", label: "Recortar espacios" },
  { id: "cleaning.cast", label: "Convertir tipos" },
  { id: "cleaning.filter_rows", label: "Excluir registros con nulos" },
  { id: "cleaning.deduplicate", label: "Deduplicar" },
];

type Form = {
  enabled: boolean;
  operations: Partial<Record<CleaningOperation, string>>; // operación → columnas («*» = todas)
  tokens: string; // una línea por columna: «columna: NA, -»
  max_excluded_rows_pct: string;
  max_nulls_created_pct: string;
  max_rounded_cells: string;
  min_output_rows: string;
  evaluate_quality_rules: boolean;
};

const EMPTY: Form = {
  enabled: false,
  operations: {},
  tokens: "",
  max_excluded_rows_pct: "0",
  max_nulls_created_pct: "0",
  max_rounded_cells: "0",
  min_output_rows: "1",
  evaluate_quality_rules: true,
};

/** Perfiles: sólo rellenan el formulario para revisarlo; nada se activa sin guardar. */
const PRESETS: Record<string, { label: string; form: Form }> = {
  conservative: {
    label: "Conservador",
    form: {
      ...EMPTY,
      enabled: true,
      operations: {
        "cleaning.trim_whitespace": "*",
        "cleaning.normalize_null_tokens": "*",
      },
    },
  },
  typed: {
    label: "Tipado",
    form: {
      ...EMPTY,
      enabled: true,
      operations: {
        "cleaning.trim_whitespace": "*",
        "cleaning.normalize_null_tokens": "*",
        "cleaning.cast": "*",
      },
    },
  },
};

function toForm(content: PolicyContent | undefined): Form {
  if (!content) return EMPTY;
  const scopes = Object.fromEntries(
    (content.column_scopes ?? []).map((s) => [
      s.operation,
      s.columns.join(", "),
    ]),
  );
  return {
    enabled: content.enabled,
    operations: Object.fromEntries(
      (content.allowed_operations ?? []).map((op) => [op, scopes[op] ?? ""]),
    ),
    tokens: (content.null_tokens_by_column ?? [])
      .map((item) => `${item.column}: ${item.tokens.join(", ")}`)
      .join("\n"),
    max_excluded_rows_pct: String(content.max_excluded_rows_pct ?? "0"),
    max_nulls_created_pct: String(content.max_nulls_created_pct ?? "0"),
    max_rounded_cells: String(content.max_rounded_cells ?? 0),
    min_output_rows: String(content.min_output_rows ?? 1),
    evaluate_quality_rules: content.evaluate_quality_rules ?? true,
  };
}

const list = (value: string) => [
  ...new Set(
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  ),
];

function toContent(form: Form): PolicyContentInput {
  const allowed = OPERATIONS.map((o) => o.id).filter(
    (id) => form.operations[id] !== undefined,
  );
  return {
    schema_version: "automation-policy@1",
    enabled: form.enabled,
    allowed_operations: allowed,
    column_scopes: allowed
      .filter((id) => list(form.operations[id] ?? "").length)
      .map((id) => ({
        operation: id,
        columns: list(form.operations[id] ?? ""),
      })),
    null_tokens_by_column: form.tokens
      .split("\n")
      .map((line) => line.split(":"))
      .filter(([column, tokens]) => column?.trim() && tokens?.trim())
      .map(([column, ...rest]) => ({
        column: column.trim(),
        tokens: list(rest.join(":")),
      })),
    max_excluded_rows_pct: form.max_excluded_rows_pct,
    max_nulls_created_pct: form.max_nulls_created_pct,
    max_rounded_cells: Number(form.max_rounded_cells),
    min_output_rows: Number(form.min_output_rows),
    evaluate_quality_rules: form.evaluate_quality_rules,
  };
}

/** Política de automatización del proyecto (Fase 11B): autoriza operaciones concretas sobre
 * columnas concretas y fija barreras; desactivada y vacía por defecto. */
export function PolicyEditor({
  projectId,
  archived,
}: {
  projectId: string;
  archived: boolean;
}) {
  const policy = useAutomationPolicy(projectId);
  const save = useSavePolicy(projectId);
  const [form, setForm] = useState<Form | null>(null);
  const current = policy.data ?? null;
  const shown = form ?? toForm(current?.content);
  const set = (patch: Partial<Form>) => setForm({ ...shown, ...patch });
  return (
    <details className="policy-editor panel-lite">
      <summary>
        <Bot size={15} /> Modo automático ·{" "}
        {policy.isPending
          ? "cargando…"
          : current
            ? `política rev ${current.revision} · ${current.content.enabled ? "activada" : "desactivada"}`
            : "sin política (desactivado)"}
      </summary>
      <p className="fine-print">
        La política aprueba en tu nombre sólo lo que autoriza: operaciones y
        columnas concretas, dentro de los límites. Lo demás pide revisión. El
        original nunca cambia y la aplicación vuelve a comprobar el efecto
        exacto.
      </p>
      <div className="policy-presets">
        {Object.entries(PRESETS).map(([id, preset]) => (
          <Button
            key={id}
            size="sm"
            variant="ghost"
            disabled={archived}
            onClick={() => setForm(preset.form)}
          >
            Perfil {preset.label}
          </Button>
        ))}
      </div>
      <label className="check-row">
        <input
          type="checkbox"
          checked={shown.enabled}
          disabled={archived}
          onChange={(e) => set({ enabled: e.target.checked })}
        />
        Activar la aprobación por política
      </label>
      <fieldset className="policy-operations">
        <legend>Operaciones autorizadas y columnas («*» = todas)</legend>
        {OPERATIONS.map((op) => {
          const on = shown.operations[op.id] !== undefined;
          return (
            <div key={op.id} className="policy-operation">
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={on}
                  disabled={archived}
                  onChange={(e) => {
                    const next = { ...shown.operations };
                    if (e.target.checked) next[op.id] = "";
                    else delete next[op.id];
                    set({ operations: next });
                  }}
                />
                {op.label}
              </label>
              {on && (
                <input
                  aria-label={`Columnas para ${op.label}`}
                  placeholder="importe, region  o  *"
                  value={shown.operations[op.id] ?? ""}
                  disabled={archived}
                  onChange={(e) =>
                    set({
                      operations: {
                        ...shown.operations,
                        [op.id]: e.target.value,
                      },
                    })
                  }
                />
              )}
            </div>
          );
        })}
      </fieldset>
      <label className="field">
        <span>
          Marcadores de nulo por columna (una línea: «columna: NA, -»)
        </span>
        <textarea
          rows={3}
          value={shown.tokens}
          disabled={archived}
          onChange={(e) => set({ tokens: e.target.value })}
        />
      </label>
      <div className="policy-limits">
        <label className="field">
          <span>Máx. filas excluidas (%)</span>
          <input
            inputMode="decimal"
            value={shown.max_excluded_rows_pct}
            disabled={archived}
            onChange={(e) => set({ max_excluded_rows_pct: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Máx. nulos creados (%)</span>
          <input
            inputMode="decimal"
            value={shown.max_nulls_created_pct}
            disabled={archived}
            onChange={(e) => set({ max_nulls_created_pct: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Máx. celdas redondeadas</span>
          <input
            inputMode="numeric"
            value={shown.max_rounded_cells}
            disabled={archived}
            onChange={(e) => set({ max_rounded_cells: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Mín. filas de salida</span>
          <input
            inputMode="numeric"
            value={shown.min_output_rows}
            disabled={archived}
            onChange={(e) => set({ min_output_rows: e.target.value })}
          />
        </label>
      </div>
      {save.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(save.error)}
        </p>
      )}
      <div className="form-footer">
        <span className="fine-print muted">
          No se convierten identificadores a número ni se publican conversiones
          fallidas, aunque la política lo permita.
        </span>
        <Button
          disabled={archived || save.isPending || !form}
          onClick={() =>
            void save
              .mutateAsync({
                expected: current?.revision ?? 0,
                content: toContent(shown),
              })
              .then(() => setForm(null))
              .catch(() => {})
          }
        >
          {save.isPending ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <Save size={16} />
          )}
          Guardar política
        </Button>
      </div>
    </details>
  );
}
