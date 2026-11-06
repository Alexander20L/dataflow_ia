"use client";
import { useState } from "react";
import { FileDown } from "lucide-react";

const PROFILES = {
  standard: {
    label: "CSV estándar",
    help: "UTF-8, coma, punto decimal: se vuelve a importar sin cambios.",
  },
  excel_regional: {
    label: "Excel regional",
    help: "Punto y coma y coma decimal (Excel en español, p. ej. Colombia).",
  },
} as const;
type Profile = keyof typeof PROFILES;

/** Descarga CSV con un perfil fijo y documentado. */
export function CsvExport({ href, label }: { href: string; label: string }) {
  const [profile, setProfile] = useState<Profile>("standard");
  return (
    <span className="csv-export">
      <select
        aria-label={`Perfil de ${label}`}
        value={profile}
        title={PROFILES[profile].help}
        onChange={(e) => setProfile(e.target.value as Profile)}
      >
        {Object.entries(PROFILES).map(([value, p]) => (
          <option key={value} value={value}>
            {p.label}
          </option>
        ))}
      </select>
      <a
        className="btn btn-outline btn-sm"
        href={`${href}?profile=${profile}`}
        title={PROFILES[profile].help}
      >
        <FileDown size={14} /> {label}
      </a>
    </span>
  );
}
