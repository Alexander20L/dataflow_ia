"use client";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { roles } from "@/features/understanding/api";
import type { ApplicableOperation, Operation } from "./api";

const outputs = {
  table: "Tabla",
  profile: "Perfil",
  quality: "Calidad",
  quality_rules: "Reglas de calidad",
};

export function requirementLabel(
  requirement: NonNullable<ApplicableOperation["missing_requirements"]>[number],
) {
  return requirement.kind === "semantic_revision"
    ? "Requiere fijar una revisión semántica"
    : `Requiere una columna confirmada como «${roles[requirement.role]}»`;
}

export function OperationPicker({
  operations,
  applicable,
  disabled,
  onAdd,
}: {
  operations: Operation[];
  applicable: ApplicableOperation[];
  disabled?: boolean;
  onAdd: (operation: Operation) => void;
}) {
  return (
    <ul className="operation-picker" aria-label="Catálogo de operaciones">
      {operations.map((operation) => {
        const status = applicable.find((item) => item.key === operation.key);
        const allowed = status?.applicable ?? false;
        return (
          <li key={operation.key} className={allowed ? "" : "unavailable"}>
            <div>
              <strong>{operation.title}</strong>
              <small className="mono">{operation.key}</small>
              <span className="badge neutral">
                {outputs[operation.output_kind]}
              </span>
              {!allowed && status?.reason && (
                <small className="muted">{status.reason}</small>
              )}
              {status?.missing_requirements?.map((requirement, index) => (
                <small key={index} className="badge review">
                  {requirementLabel(requirement)}
                </small>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={disabled || !allowed}
              aria-label={`Añadir ${operation.title}`}
              onClick={() => onAdd(operation)}
            >
              <Plus size={14} />
              Añadir
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
