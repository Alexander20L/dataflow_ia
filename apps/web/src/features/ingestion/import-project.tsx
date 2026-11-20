"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Files,
  LockKeyhole,
  Network,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/lib/providers";
import { useCreateProject } from "@/features/projects/api";
import { errorMessage } from "@/lib/api";
import {
  useImportDatabase,
  useInspectDatabase,
  useInspectRelated,
  useUploadFile,
  useUploadRelated,
  type DataModel,
} from "./api";
import { DataModelView } from "./related-sources";
import {
  DatabaseFields,
  EMPTY_DATABASE,
  databaseProblem,
  type DatabaseForm,
} from "./database-fields";
import { FILE_ACCEPT, fileProblem } from "./csv-workspace";

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(3, "Escribe al menos 3 caracteres.")
    .max(80, "Máximo 80 caracteres."),
  description: z.string().max(300, "Máximo 300 caracteres."),
});
type FormData = z.infer<typeof schema>;

/** Fase 31: tres formas de traer los datos. */
const MODES = [
  {
    id: "file",
    label: "Cargar archivo",
    hint: "Un CSV, Excel o PDF con tablas",
    icon: UploadCloud,
  },
  {
    id: "related",
    label: "Cargar varios archivos relacionados",
    hint: "De 2 a 5 CSV o Excel que comparten claves",
    icon: Files,
  },
  {
    id: "database",
    label: "Conectar base de datos",
    hint: "SQL Server o PostgreSQL",
    icon: Database,
  },
] as const;
type Mode = (typeof MODES)[number]["id"];
const MAX_RELATED = 5;
const RELATED_ACCEPT = ".csv,.xlsx,text/csv";

function relatedProblem(file: File) {
  if (!/\.(csv|xlsx)$/i.test(file.name))
    return `«${file.name}»: en esta opción sólo se admiten CSV o Excel (.xlsx).`;
  if (!file.size) return `«${file.name}» está vacío.`;
  if (file.size > 5 * 1024 * 1024) return `«${file.name}» supera 5 MB.`;
  return null;
}

function baseName(name: string) {
  return name.replace(/\.(csv|xlsx|pdf)$/i, "").trim();
}

export function ImportProject() {
  const { notify } = useApp();
  const createProject = useCreateProject();
  const uploadFile = useUploadFile();
  const uploadRelated = useUploadRelated();
  const importDatabase = useImportDatabase();
  const inspectDatabase = useInspectDatabase();
  const inspectRelated = useInspectRelated();
  const [model, setModel] = useState<DataModel | null>(null);
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const relatedInput = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [related, setRelated] = useState<File[]>([]);
  const [database, setDatabase] = useState<DatabaseForm>(EMPTY_DATABASE);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const {
    register,
    handleSubmit,
    getValues,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", description: "" },
  });
  function suggestName(base: string) {
    if (getValues("name").trim() || !base) return;
    setValue(
      "name",
      (base.length >= 3 ? base : `Análisis de ${base}`).slice(0, 80),
      { shouldValidate: true },
    );
  }
  function selectFile(selected?: File) {
    if (!selected) return;
    setError("");
    setFile(null);
    const problem = fileProblem(selected);
    if (problem) {
      setError(problem);
      return;
    }
    setFile(selected);
    suggestName(baseName(selected.name));
  }
  function addRelated(selected: FileList | File[] | null | undefined) {
    if (!selected) return;
    setError("");
    const next = [...related];
    for (const item of Array.from(selected)) {
      const problem = relatedProblem(item);
      if (problem) {
        setError(problem);
        continue;
      }
      if (next.some((f) => f.name.toLowerCase() === item.name.toLowerCase()))
        continue;
      if (next.length >= MAX_RELATED) {
        setError(`Como mucho ${MAX_RELATED} archivos.`);
        break;
      }
      next.push(item);
    }
    setRelated(next);
    setModel(null);
    if (next.length) suggestName(baseName(next[0].name));
    if (relatedInput.current) relatedInput.current.value = "";
  }
  function choose(next: Mode) {
    setMode(next);
    setError("");
    setModel(null);
  }
  /** Problema de lo elegido en «varios archivos» o «base de datos», o null. */
  function sourceProblem() {
    if (mode === "related" && related.length < 2)
      return "Elige al menos 2 archivos relacionados.";
    if (mode === "database") return databaseProblem(database);
    return null;
  }
  function connection() {
    const common = {
      server: database.server.trim(),
      port: Number(database.port),
      database: database.database.trim(),
      user: database.user.trim(),
      password: database.password,
    };
    return database.engine === "sqlserver"
      ? ({
          engine: "sqlserver",
          connection: {
            ...common,
            schema_name: database.schema.trim() || null,
          },
        } as const)
      : ({
          engine: "postgresql",
          connection: {
            ...common,
            schema_name: database.schema.trim(),
            // Fase 32: sólo se usa en el modo público; vacío, ninguno.
            ca_certificate: database.certificate.trim() || null,
          },
        } as const);
  }
  async function ensureProject(data: FormData) {
    return (
      createProject.data ??
      (await createProject.mutateAsync({
        name: data.name,
        description: data.description,
        file_name: mode === "related" ? related[0].name : null,
      }))
    );
  }
  /** Fase 31: «Ver esquema»: la foto del modelo de datos antes de analizar (no guarda nada). */
  async function preview(data: FormData) {
    setError("");
    const problem = sourceProblem();
    if (problem) {
      setError(problem);
      return;
    }
    try {
      const project = await ensureProject(data);
      setModel(
        mode === "related"
          ? await inspectRelated.mutateAsync({
              files: related,
              projectId: project.id,
            })
          : await inspectDatabase.mutateAsync({
              ...connection(),
              projectId: project.id,
            }),
      );
    } catch (failure) {
      setModel(null);
      setError(errorMessage(failure));
    }
  }
  async function submit(data: FormData) {
    setError("");
    const problem = sourceProblem();
    if (problem) {
      setError(problem);
      return;
    }
    try {
      const project =
        createProject.data ??
        (await createProject.mutateAsync({
          name: data.name,
          description: data.description,
          file_name:
            mode === "file"
              ? (file?.name ?? null)
              : mode === "related"
                ? related[0].name
                : null,
        }));
      if (mode === "file") {
        if (file) await uploadFile.mutateAsync({ file, projectId: project.id });
        notify(
          file
            ? "Original conservado. Procesamiento encolado."
            : "Proyecto guardado. Puedes subir su primer archivo desde el espacio de trabajo.",
        );
      } else if (mode === "related") {
        const version = await uploadRelated.mutateAsync({
          files: related,
          projectId: project.id,
        });
        notify(
          version.source_origin?.joined
            ? "Archivos relacionados y unidos. Análisis encolado."
            : "Archivos conservados. No se encontró una clave común: se analizan por separado.",
        );
      } else {
        const version = await importDatabase.mutateAsync({
          ...connection(),
          projectId: project.id,
        });
        setDatabase((current) => ({ ...current, password: "" }));
        notify(
          version.source_origin?.joined
            ? "Tablas copiadas y unidas por sus claves. Análisis encolado."
            : "Tablas copiadas. Análisis encolado.",
        );
      }
      router.push(`/workspace/${project.id}`);
    } catch (problem) {
      if (mode === "database")
        setDatabase((current) => ({ ...current, password: "" }));
      setError(errorMessage(problem));
    }
  }
  return (
    <>
      <Link className="back-link" href="/projects">
        <ArrowLeft size={16} />
        Volver a proyectos
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">UN NUEVO PUNTO DE PARTIDA</p>
          <h1>Crea tu próximo análisis</h1>
          <p>
            Sube un archivo, varios archivos relacionados o conecta una base de
            datos, y obtén indicadores y gráficos sin configurar el análisis.
          </p>
        </div>
        <span className="badge calculated">Análisis automático</span>
      </div>
      <div className="import-layout">
        <form className="panel import-form" onSubmit={handleSubmit(submit)}>
          <div className="section-title">
            <span className="section-number">01</span>
            <div>
              <h2>Identifica tu análisis</h2>
              <p>
                Al elegir tus datos, el nombre se completa automáticamente.
                Puedes cambiarlo.
              </p>
            </div>
          </div>
          <label htmlFor="project-name">
            Nombre del proyecto <span className="required">*</span>
          </label>
          <input
            id="project-name"
            placeholder="Ej. Rendimiento comercial 2026"
            aria-invalid={!!errors.name}
            readOnly={!!createProject.data}
            {...register("name")}
          />
          {errors.name && (
            <p className="field-error" role="alert">
              {errors.name.message}
            </p>
          )}
          <label htmlFor="project-description">
            Descripción <span className="muted">(opcional)</span>
          </label>
          <textarea
            id="project-description"
            rows={3}
            placeholder="¿Qué te gustaría descubrir con este análisis?"
            readOnly={!!createProject.data}
            {...register("description")}
          />
          {errors.description && (
            <p className="field-error">{errors.description.message}</p>
          )}
          <div className="section-title second-section">
            <span className="section-number">02</span>
            <div>
              <h2>Añade tus datos</h2>
              <p>
                Elige cómo traerlos. También puedes crear el proyecto vacío.
              </p>
            </div>
          </div>
          <div
            className="source-modes"
            role="radiogroup"
            aria-label="Cómo traer los datos"
          >
            {MODES.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={mode === item.id}
                  className={mode === item.id ? "selected" : ""}
                  onClick={() => choose(item.id)}
                >
                  <Icon size={20} aria-hidden />
                  <strong>{item.label}</strong>
                  <small>{item.hint}</small>
                </button>
              );
            })}
          </div>
          {mode === "file" && (
            <>
              <input
                ref={input}
                hidden
                type="file"
                accept={FILE_ACCEPT}
                onChange={(e) => selectFile(e.target.files?.[0])}
              />
              <div
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  selectFile(e.dataTransfer.files[0]);
                }}
              >
                <span className="upload-icon">
                  <UploadCloud size={29} />
                </span>
                <h3>Arrastra tu archivo hasta aquí</h3>
                <p>o selecciona uno desde tu equipo</p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => input.current?.click()}
                >
                  Seleccionar archivo
                </Button>
                <small>CSV, Excel (.xlsx) o PDF con tablas · hasta 5 MB</small>
              </div>
              {file && (
                <div className="selected-file">
                  <FileSpreadsheet size={25} />
                  <span>
                    <strong>{file.name}</strong>
                    <small>
                      {(file.size / 1024).toFixed(1)} KB · seleccionado, sin
                      subir
                    </small>
                  </span>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Quitar archivo"
                    onClick={() => {
                      setFile(null);
                      if (input.current) input.current.value = "";
                    }}
                  >
                    <X size={17} />
                  </button>
                </div>
              )}
            </>
          )}
          {mode === "related" && (
            <>
              <input
                ref={relatedInput}
                hidden
                multiple
                type="file"
                accept={RELATED_ACCEPT}
                aria-label="Archivos relacionados"
                onChange={(e) => addRelated(e.target.files)}
              />
              <div
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  addRelated(e.dataTransfer.files);
                }}
              >
                <span className="upload-icon">
                  <Files size={29} />
                </span>
                <h3>Arrastra de 2 a 5 archivos relacionados</h3>
                <p>
                  Por ejemplo: estudiantes, asistencia y carreras. El sistema
                  busca las columnas que los unen (como «id_estudiante»).
                </p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => relatedInput.current?.click()}
                >
                  Seleccionar archivos
                </Button>
                <small>CSV o Excel (.xlsx) · hasta 5 MB cada uno</small>
              </div>
              {related.length > 0 && (
                <ul
                  className="selected-files"
                  aria-label="Archivos seleccionados"
                >
                  {related.map((item) => (
                    <li key={item.name} className="selected-file">
                      <FileSpreadsheet size={22} />
                      <span>
                        <strong>{item.name}</strong>
                        <small>{(item.size / 1024).toFixed(1)} KB</small>
                      </span>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Quitar ${item.name}`}
                        onClick={() => {
                          setModel(null);
                          setRelated((current) =>
                            current.filter((f) => f !== item),
                          );
                        }}
                      >
                        <X size={17} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {mode === "database" && (
            <DatabaseFields
              value={database}
              onChange={(next) => {
                setDatabase(next);
                setModel(null);
                suggestName(next.database.trim());
              }}
            />
          )}
          {(mode === "related" || mode === "database") && (
            <div className="schema-preview">
              <Button
                type="button"
                variant="outline"
                disabled={
                  isSubmitting ||
                  inspectRelated.isPending ||
                  inspectDatabase.isPending
                }
                onClick={() => void handleSubmit(preview)()}
              >
                <Network size={16} />
                {inspectRelated.isPending || inspectDatabase.isPending
                  ? "Leyendo el esquema…"
                  : "Ver esquema"}
              </Button>
              <small>
                Muestra las tablas, sus claves y cómo se relacionan antes de
                analizar. No guarda nada.
              </small>
            </div>
          )}
          {model && mode !== "file" && (
            <section className="related-sources" aria-label="Esquema">
              <header>
                <Network size={16} aria-hidden />
                <div>
                  <h3>Esquema que se analizará</h3>
                  <p>
                    {model.views.length > 0
                      ? `Se analizan ${model.tables.length} tablas y ${model.views.length} vistas; se abre primero «${model.main}».`
                      : "No se encontraron claves comunes: cada tabla se analiza por separado."}
                    {(model.omitted ?? []).length > 0 &&
                      ` No se copian: ${(model.omitted ?? []).map((o) => `${o.table} (${o.reason})`).join("; ")}.`}
                  </p>
                </div>
              </header>
              <DataModelView
                tables={model.tables}
                relations={model.relations}
                views={model.views}
                main={model.main}
              />
            </section>
          )}
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          {error && createProject.data && (
            <p className="fine-print">
              El proyecto ya está guardado; puedes reintentar la carga sin crear
              otro.{" "}
              <Link
                className="text-link"
                href={`/workspace/${createProject.data.id}`}
              >
                Abrir proyecto
              </Link>
            </p>
          )}
          {isSubmitting && (
            <p className="fine-print" role="status">
              {mode === "database"
                ? "Copiando las tablas de la base…"
                : mode === "related"
                  ? "Leyendo los archivos y buscando sus relaciones…"
                  : file
                    ? "Guardando el proyecto y enviando el archivo…"
                    : "Guardando el proyecto…"}
            </p>
          )}
          <div className="info-banner">
            <ShieldCheck size={18} />
            <span>
              {mode === "related"
                ? "Cada archivo se conserva y se analiza por separado. Si comparten claves, también se analizan unidos, sin repetir ni perder registros."
                : mode === "database"
                  ? "Se copian las tablas principales; si sus claves las relacionan, también se analizan unidas. La base no se modifica."
                  : "El original se conserva sin cambios. El sistema elige la hoja de un Excel, genera la copia analítica, el perfil, la calidad y el dashboard automáticamente."}
            </span>
          </div>
          <div className="form-footer">
            <Button asChild variant="ghost">
              <Link href="/">Cancelar</Link>
            </Button>
            <Button disabled={isSubmitting} type="submit">
              Continuar al análisis <ArrowRight size={16} />
            </Button>
          </div>
        </form>
        <aside>
          <section className="panel import-aside">
            <span className="metric-icon indigo">
              <Database size={22} />
            </span>
            <h2>De tus datos a una visión completa</h2>
            <p>Sube los datos; el sistema prepara el primer dashboard.</p>
            <ol className="benefits-list">
              <li>
                <CheckCircle2 size={17} />
                <span>Entiende la estructura de tus datos</span>
              </li>
              <li>
                <CheckCircle2 size={17} />
                <span>Une tablas relacionadas por sus claves</span>
              </li>
              <li>
                <CheckCircle2 size={17} />
                <span>Calidad evaluada automáticamente</span>
              </li>
              <li>
                <CheckCircle2 size={17} />
                <span>Indicadores y gráficos sin confirmaciones</span>
              </li>
              <li>
                <CheckCircle2 size={17} />
                <span>Encuentra patrones con evidencia</span>
              </li>
            </ol>
            <hr />
            <p className="security-note">
              <LockKeyhole size={16} />
              El original siempre permanece intacto.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
