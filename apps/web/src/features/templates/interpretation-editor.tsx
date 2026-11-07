"use client";
import { useState } from "react";
import { LoaderCircle, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useRepresentations } from "@/features/executions/api";
import {
  useMappings,
  useSaveMapping,
  useTemplateCandidates,
  type MappingContent,
  type TemplateCandidate,
} from "./api";

type RoleForm = { column: string; target_type: string; scale: string };

/**
 * Interpretación confirmada (Fase 11D): el molde candidato sólo rellena el formulario; la
 * persona elige columnas, tipo, moneda o unidad y grano, y guarda. Después el pipeline puede
 * reanudarse y reprocesar la carga con esta interpretación.
 */
export function InterpretationEditor({
  projectId,
  versionId,
  onSaved,
}: {
  projectId: string;
  versionId: string;
  onSaved: () => void;
}) {
  const tables = useRepresentations(versionId);
  const table = tables.data?.[0];
  const candidates = useTemplateCandidates(table?.id ?? "");
  const mappings = useMappings(projectId);
  const save = useSaveMapping(projectId);
  const [template, setTemplate] = useState<string | null>(null);
  const [roles, setRoles] = useState<Record<string, RoleForm>>({});
  const [currency, setCurrency] = useState("");
  const [unit, setUnit] = useState("");
  const [grain, setGrain] = useState("");
  const options = (candidates.data ?? []).filter(
    (c) => c.template !== "generic@1",
  );
  const chosen: TemplateCandidate | undefined =
    options.find((c) => c.template === template) ?? options[0];
  if (tables.isPending || candidates.isPending)
    return <p className="fine-print">Buscando moldes candidatos…</p>;
  if (!table?.columns || !chosen)
    return (
      <p className="fine-print">No hay moldes candidatos para esta tabla.</p>
    );
  const columns = table.columns.map((c) => String(c.name));
  const value = (role: string): RoleForm => {
    const found = chosen.roles.find((r) => r.role === role);
    return (
      roles[`${chosen.template}:${role}`] ?? {
        column: found?.column ?? "",
        target_type: found?.target_type ?? "string",
        scale: found?.scale != null ? String(found.scale) : "2",
      }
    );
  };
  const setRole = (role: string, patch: Partial<RoleForm>) =>
    setRoles({
      ...roles,
      [`${chosen.template}:${role}`]: { ...value(role), ...patch },
    });
  const existing = (mappings.data ?? []).find(
    (m) => m.template === chosen.template,
  );
  function content(): MappingContent {
    return {
      schema_version: "template-mapping@1",
      template: chosen!.template,
      roles: chosen!.roles
        .filter((r) => value(r.role).column)
        .map((r) => {
          const form = value(r.role);
          return {
            role: r.role,
            column: form.column,
            target_type: form.target_type as "string",
            scale: form.target_type === "decimal" ? Number(form.scale) : null,
          };
        }),
      currency: currency.trim().toUpperCase() || null,
      unit: unit.trim() || null,
      grain: grain.trim() || null,
    };
  }
  return (
    <div className="interpretation-editor">
      <label className="field">
        <span>Molde</span>
        <select
          value={chosen.template}
          onChange={(e) => setTemplate(e.target.value)}
        >
          {options.map((c) => (
            <option key={c.template} value={c.template}>
              {c.label}
              {c.complete ? "" : " (incompleto)"}
            </option>
          ))}
        </select>
      </label>
      {chosen.roles.map((role) => {
        const form = value(role.role);
        return (
          <div key={role.role} className="policy-operation">
            <span>
              {role.label}
              {role.required ? " *" : ""}
            </span>
            <select
              aria-label={`Columna para ${role.label}`}
              value={form.column}
              onChange={(e) => setRole(role.role, { column: e.target.value })}
            >
              <option value="">—</option>
              {columns.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <select
              aria-label={`Tipo para ${role.label}`}
              value={form.target_type}
              onChange={(e) =>
                setRole(role.role, { target_type: e.target.value })
              }
            >
              {["string", "integer", "decimal", "date"].map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
            {form.target_type === "decimal" && (
              <input
                aria-label={`Decimales para ${role.label}`}
                inputMode="numeric"
                value={form.scale}
                onChange={(e) => setRole(role.role, { scale: e.target.value })}
              />
            )}
          </div>
        );
      })}
      <div className="policy-limits">
        <label className="field">
          <span>Moneda (ISO, p. ej. PEN)</span>
          <input
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Unidad</span>
          <input value={unit} onChange={(e) => setUnit(e.target.value)} />
        </label>
        <label className="field">
          <span>Grano (qué es cada fila)</span>
          {chosen.grains ? (
            <select value={grain} onChange={(e) => setGrain(e.target.value)}>
              <option value="">—</option>
              {chosen.grains.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          ) : (
            <input value={grain} onChange={(e) => setGrain(e.target.value)} />
          )}
        </label>
      </div>
      {save.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(save.error)}
        </p>
      )}
      <Button
        disabled={save.isPending}
        onClick={() =>
          void save
            .mutateAsync({
              expected: existing?.revision ?? 0,
              content: content(),
            })
            .then(onSaved)
            .catch(() => {})
        }
      >
        {save.isPending ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Save size={16} />
        )}
        Confirmar interpretación
      </Button>
    </div>
  );
}
