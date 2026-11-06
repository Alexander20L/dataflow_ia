"use client";

type Schema = {
  title?: string;
  description?: string;
  type?: string;
  const?: unknown;
  enum?: unknown[];
  default?: unknown;
  anyOf?: Schema[];
  items?: Schema;
  "x-dataflow-column-ref"?: boolean;
};
type ObjectSchema = {
  properties?: Record<string, Schema>;
  required?: string[];
};
export type ColumnOption = { id: string; name: string };

const display = (value: unknown) =>
  value === "\t"
    ? "Tabulador"
    : value === null
      ? "Sin valor"
      : typeof value === "string"
        ? value
        : JSON.stringify(value);

/** Une `T | None` en un solo esquema con la marca de nulo admitido. */
function unwrap(schema: Schema): { schema: Schema; nullable: boolean } {
  const variants = schema.anyOf?.filter((item) => item.type !== "null");
  if (schema.anyOf && variants?.length === 1)
    return {
      schema: { ...variants[0], title: schema.title, default: schema.default },
      nullable: true,
    };
  return { schema, nullable: false };
}

export function ParameterForm({
  schema,
  value,
  columns,
  idPrefix,
  disabled,
  onChange,
}: {
  schema: Record<string, unknown>;
  value: Record<string, unknown>;
  columns: ColumnOption[];
  idPrefix: string;
  disabled?: boolean;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const { properties = {}, required = [] } = schema as ObjectSchema;
  const entries = Object.entries(properties);
  if (!entries.length)
    return <p className="fine-print muted">Sin parámetros.</p>;
  const set = (name: string, next: unknown) =>
    onChange({ ...value, [name]: next });
  return (
    <div className="parameter-form">
      {entries.map(([name, raw]) => {
        const { schema: field, nullable } = unwrap(raw);
        const id = `${idPrefix}-${name}`;
        const current = name in value ? value[name] : field.default;
        const label = (
          <label htmlFor={id}>
            {field.title ?? name}
            {required.includes(name) && !(name in value) && (
              <span className="badge review">Obligatorio</span>
            )}
          </label>
        );
        if (field["x-dataflow-column-ref"]) {
          if (field.type === "array") {
            const selected = Array.isArray(current) ? current : [];
            return (
              <fieldset key={name} className="parameter-field" id={id}>
                <legend>{field.title ?? name}</legend>
                {columns.map((column) => (
                  <label key={column.id} className="check-option">
                    <input
                      type="checkbox"
                      disabled={disabled}
                      checked={selected.includes(column.id)}
                      onChange={(e) =>
                        set(
                          name,
                          e.target.checked
                            ? [...selected, column.id]
                            : selected.filter((item) => item !== column.id),
                        )
                      }
                    />
                    {column.name}
                  </label>
                ))}
              </fieldset>
            );
          }
          return (
            <div key={name} className="parameter-field">
              {label}
              <select
                id={id}
                disabled={disabled}
                value={typeof current === "string" ? current : ""}
                onChange={(e) => set(name, e.target.value || undefined)}
              >
                <option value="">Selecciona una columna</option>
                {columns.map((column) => (
                  <option key={column.id} value={column.id}>
                    {column.name}
                  </option>
                ))}
              </select>
            </div>
          );
        }
        if ("const" in field)
          return (
            <div key={name} className="parameter-field">
              <span className="parameter-label">{field.title ?? name}</span>
              <output className="mono" title="Fijado por el catálogo">
                {display(field.const)}
              </output>
            </div>
          );
        if (field.enum) {
          const options = [...field.enum, ...(nullable ? [null] : [])];
          const index = options.findIndex(
            (option) => JSON.stringify(option) === JSON.stringify(current),
          );
          return (
            <div key={name} className="parameter-field">
              {label}
              <select
                id={id}
                disabled={disabled}
                value={index < 0 ? "" : String(index)}
                onChange={(e) =>
                  set(
                    name,
                    e.target.value === ""
                      ? undefined
                      : options[Number(e.target.value)],
                  )
                }
              >
                {index < 0 && <option value="">Selecciona un valor</option>}
                {options.map((option, i) => (
                  <option key={i} value={i}>
                    {display(option)}
                  </option>
                ))}
              </select>
            </div>
          );
        }
        if (field.type === "array" && field.items?.enum) {
          const selected = Array.isArray(current) ? current : [];
          return (
            <fieldset key={name} className="parameter-field" id={id}>
              <legend>{field.title ?? name}</legend>
              {field.items.enum.map((option) => (
                <label key={String(option)} className="check-option">
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={selected.includes(option)}
                    onChange={(e) =>
                      set(
                        name,
                        e.target.checked
                          ? field.items!.enum!.filter(
                              (item) =>
                                item === option || selected.includes(item),
                            )
                          : selected.filter((item) => item !== option),
                      )
                    }
                  />
                  {display(option)}
                </label>
              ))}
            </fieldset>
          );
        }
        if (field.type === "boolean")
          return (
            <label key={name} className="check-option parameter-field">
              <input
                id={id}
                type="checkbox"
                disabled={disabled}
                checked={current === true}
                onChange={(e) => set(name, e.target.checked)}
              />
              {field.title ?? name}
            </label>
          );
        // Parámetros estructurados (p. ej. referencias a métricas o filtros): se definen desde
        // su pantalla y aquí sólo se muestran; un campo de texto los corrompería.
        if (
          (typeof current === "object" && current !== null) ||
          field.type === "object" ||
          field.type === "array"
        )
          return (
            <div key={name} className="parameter-field">
              {label}
              <output className="mono">
                {JSON.stringify(current ?? null)}
              </output>
              <small className="muted">
                Se define desde su pantalla (por ejemplo, Análisis); aquí sólo
                se muestra.
              </small>
            </div>
          );
        return (
          <div key={name} className="parameter-field">
            {label}
            <input
              id={id}
              disabled={disabled}
              type={field.type === "integer" ? "number" : "text"}
              value={
                current === undefined || current === null ? "" : String(current)
              }
              onChange={(e) =>
                set(
                  name,
                  e.target.value === ""
                    ? undefined
                    : field.type === "integer"
                      ? Number.parseInt(e.target.value, 10)
                      : e.target.value,
                )
              }
            />
          </div>
        );
      })}
    </div>
  );
}
