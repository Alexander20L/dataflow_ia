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
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/lib/providers";
import { useCreateProject } from "@/features/projects/api";
import { errorMessage } from "@/lib/api";
import { useUploadCsv } from "./api";

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(3, "Escribe al menos 3 caracteres.")
    .max(80, "Máximo 80 caracteres."),
  description: z.string().max(300, "Máximo 300 caracteres."),
});
type FormData = z.infer<typeof schema>;
export function ImportProject() {
  const { notify } = useApp();
  const createProject = useCreateProject();
  const uploadCsv = useUploadCsv();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [example, setExample] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", description: "" },
  });
  function selectFile(selected?: File) {
    if (!selected) return;
    setError("");
    setFile(null);
    if (/\.xlsx$/i.test(selected.name)) {
      setError(
        "Para un libro de Excel, crea el proyecto y súbelo desde su espacio de trabajo: allí eliges la hoja y revisas la vista previa.",
      );
      return;
    }
    if (!/\.csv$/i.test(selected.name)) {
      setError("Selecciona un archivo CSV.");
      return;
    }
    if (selected.size > 5 * 1024 * 1024) {
      setError("El CSV debe tener como máximo 5 MB.");
      return;
    }
    if (selected.size === 0) {
      setError("El archivo está vacío.");
      return;
    }
    setFile(selected);
    setExample(false);
  }
  async function submit(data: FormData) {
    setError("");
    if (example) {
      notify("Ejemplo de ventas listo. No se ha subido ningún archivo.");
      router.push("/workspace/ventas-2026");
      return;
    }
    try {
      const project =
        createProject.data ??
        (await createProject.mutateAsync({
          name: data.name,
          description: data.description,
          file_name: file?.name ?? null,
        }));
      if (file) await uploadCsv.mutateAsync({ file, projectId: project.id });
      notify(
        file
          ? "CSV original conservado. Procesamiento encolado."
          : "Proyecto guardado. Puedes subir su primer CSV desde el workspace.",
      );
      router.push(`/workspace/${project.id}`);
    } catch (error) {
      setError(errorMessage(error));
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
          <p>Organiza tu proyecto y elige los datos que quieres explorar.</p>
        </div>
        <span className="badge calculated">Paso 1 de 9 · Ingesta</span>
      </div>
      <div className="import-layout">
        <form className="panel import-form" onSubmit={handleSubmit(submit)}>
          <div className="section-title">
            <span className="section-number">01</span>
            <div>
              <h2>Dale un nombre a tu proyecto</h2>
              <p>Un espacio para tus datos, hallazgos y decisiones.</p>
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
                Opcional: selecciona un archivo, crea el proyecto vacío o abre
                el ejemplo.
              </p>
            </div>
          </div>
          <input
            ref={input}
            hidden
            type="file"
            accept=".csv,text/csv"
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
            <small>
              CSV UTF-8 · hasta 5 MB · Excel (.xlsx) desde el espacio de trabajo
            </small>
          </div>
          {file && (
            <div className="selected-file">
              <FileSpreadsheet size={25} />
              <span>
                <strong>{file.name}</strong>
                <small>
                  {(file.size / 1024).toFixed(1)} KB · seleccionado, sin subir
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
          <button
            type="button"
            className={`example-picker ${example ? "selected" : ""}`}
            onClick={() => {
              setExample((v) => !v);
              setFile(null);
              setError("");
            }}
          >
            <span className="example-icon">
              <Sparkles size={20} />
            </span>
            <span>
              <strong>Prefiero explorar un ejemplo</strong>
              <small>Ventas 2026 · 240 registros · 6 columnas</small>
            </span>
            {example ? <CheckCircle2 size={20} /> : <ArrowRight size={19} />}
          </button>
          {example && (
            <div className="preview-mini">
              <strong>Vista previa · datos sintéticos</strong>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Región</th>
                      <th>Categoría</th>
                      <th>Importe</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>V-0001</td>
                      <td>Norte</td>
                      <td>Tecnología</td>
                      <td>
                        <span className="null-value">nulo</span>
                      </td>
                    </tr>
                    <tr>
                      <td>V-0002</td>
                      <td>Sur</td>
                      <td>Hogar</td>
                      <td>277 €</td>
                    </tr>
                    <tr>
                      <td>V-0003</td>
                      <td>Este</td>
                      <td>Oficina</td>
                      <td>414 €</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
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
              {file
                ? "Guardando el proyecto y enviando el CSV…"
                : "Guardando el proyecto…"}
            </p>
          )}
          <div className="info-banner">
            <ShieldCheck size={18} />
            <span>
              El CSV original se conserva sin cambios. Un worker genera su copia
              analítica, el perfil y las incidencias de calidad. El ejemplo de
              ventas sigue siendo independiente de tus archivos.
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
            <h2>De un archivo a una visión completa</h2>
            <p>Un proceso claro, con el control en tus manos.</p>
            <ol className="benefits-list">
              <li>
                <CheckCircle2 size={17} />
                <span>Entiende la estructura de tus datos</span>
              </li>
              <li>
                <CheckCircle2 size={17} />
                <span>Revisa su calidad antes de analizar</span>
              </li>
              <li>
                <CheckCircle2 size={17} />
                <span>Aprueba cada transformación</span>
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
          <section className="panel connections-panel">
            <h3>¿Tus datos están en una base?</h3>
            <p>Conecta una fuente con permisos de lectura.</p>
            {["PostgreSQL", "MySQL"].map((name) => (
              <div className="connection" key={name}>
                <Database size={18} />
                <strong>{name}</strong>
                <span className="badge neutral">Próximamente</span>
              </div>
            ))}
          </section>
        </aside>
      </div>
    </>
  );
}
