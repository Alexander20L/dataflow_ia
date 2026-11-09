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
  UploadCloud,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/lib/providers";
import { useCreateProject } from "@/features/projects/api";
import { errorMessage } from "@/lib/api";
import { useUploadFile } from "./api";
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
export function ImportProject() {
  const { notify } = useApp();
  const createProject = useCreateProject();
  const uploadFile = useUploadFile();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
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
    if (!getValues("name").trim()) {
      const base = selected.name.replace(/\.(csv|xlsx)$/i, "").trim();
      setValue(
        "name",
        (base.length >= 3 ? base : `Análisis de ${base}`).slice(0, 80),
        {
          shouldValidate: true,
        },
      );
    }
  }
  async function submit(data: FormData) {
    setError("");
    try {
      const project =
        createProject.data ??
        (await createProject.mutateAsync({
          name: data.name,
          description: data.description,
          file_name: file?.name ?? null,
        }));
      if (file) await uploadFile.mutateAsync({ file, projectId: project.id });
      notify(
        file
          ? "Original conservado. Procesamiento encolado."
          : "Proyecto guardado. Puedes subir su primer archivo desde el espacio de trabajo.",
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
          <p>
            Sube tu CSV o Excel y obtén indicadores y gráficos sin configurar el
            análisis.
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
                Al elegir un archivo, el nombre se completa automáticamente.
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
              <p>Opcional: selecciona un archivo o crea el proyecto vacío.</p>
            </div>
          </div>
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
            <small>CSV UTF-8 o Excel (.xlsx) · hasta 5 MB</small>
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
                ? "Guardando el proyecto y enviando el archivo…"
                : "Guardando el proyecto…"}
            </p>
          )}
          <div className="info-banner">
            <ShieldCheck size={18} />
            <span>
              El original se conserva sin cambios. El sistema elige la hoja de
              un Excel, genera la copia analítica, el perfil, la calidad y el
              dashboard automáticamente.
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
            <p>Sube los datos; el sistema prepara el primer dashboard.</p>
            <ol className="benefits-list">
              <li>
                <CheckCircle2 size={17} />
                <span>Entiende la estructura de tus datos</span>
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
