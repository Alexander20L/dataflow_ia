"use client";
import { useState } from "react";
import Link from "next/link";
import { Archive, ArrowLeft, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import { CsvWorkspace } from "@/features/ingestion/csv-workspace";
import {
  useArchiveProject,
  useProject,
  useUpdateProject,
  type ApiProject,
} from "./api";

export function ProjectDetail({ id }: { id: string }) {
  const query = useProject(id);
  const [editing, setEditing] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const archive = useArchiveProject();
  const { notify } = useApp();
  if (query.isPending)
    return (
      <div className="loading-screen" aria-label="Cargando proyecto">
        <div className="skeleton" />
      </div>
    );
  if (query.isError)
    return (
      <div className="empty-state">
        <h1>No se pudo abrir el proyecto</h1>
        <p>{errorMessage(query.error)}</p>
        <Button onClick={() => void query.refetch()}>Reintentar</Button>
        <Link href="/projects" className="text-link">
          Volver a proyectos
        </Link>
      </div>
    );
  const project = query.data;
  return (
    <>
      <Link className="back-link" href="/projects">
        <ArrowLeft size={16} />
        Proyectos
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PROYECTO GUARDADO EN TU CUENTA</p>
          <h1>{project.name}</h1>
          <p>{project.description || "Tu nuevo espacio de análisis."}</p>
        </div>
        <div className="heading-actions">
          <Button
            variant="outline"
            size="sm"
            disabled={project.status === "archived"}
            onClick={() => setEditing(true)}
          >
            <Pencil size={15} />
            Editar proyecto
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={project.status === "archived"}
            onClick={() => setArchiving(true)}
          >
            <Archive size={15} />
            Archivar
          </Button>
        </div>
      </div>
      <div className="project-revision">
        <span className="badge neutral">
          {project.status === "archived" ? "Archivado" : "Borrador"} · revisión{" "}
          {project.revision}
        </span>
        <small className="muted">
          Actualizado: {new Date(project.updated_at).toLocaleString("es-ES")}
        </small>
      </div>
      <CsvWorkspace
        projectId={project.id}
        archived={project.status === "archived"}
      />
      {editing && (
        <EditProject project={project} onClose={() => setEditing(false)} />
      )}
      {archiving && (
        <Dialog
          title="¿Archivar este proyecto?"
          onClose={() => setArchiving(false)}
        >
          <p className="dialog-copy">
            El proyecto seguirá guardado y visible en el filtro de archivados.
            No podrá editarse mientras esté archivado.
          </p>
          {archive.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(archive.error)}
            </p>
          )}
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setArchiving(false)}>
              Cancelar
            </Button>
            <Button
              disabled={archive.isPending}
              onClick={async () => {
                try {
                  await archive.mutateAsync(project);
                  setArchiving(false);
                  notify("Proyecto archivado.");
                } catch {
                  /* Error visible en el diálogo. */
                }
              }}
            >
              Confirmar archivo
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}

function EditProject({
  project,
  onClose,
}: {
  project: ApiProject;
  onClose: () => void;
}) {
  const update = useUpdateProject();
  const { notify } = useApp();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  return (
    <Dialog title="Editar proyecto" onClose={onClose}>
      <form
        className="auth-form"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await update.mutateAsync({
              id: project.id,
              body: {
                name: name.trim(),
                description,
                expected_revision: project.revision,
              },
            });
            notify("Proyecto actualizado.");
            onClose();
          } catch {
            /* Error visible. */
          }
        }}
      >
        <label htmlFor="edit-project-name">Nombre del proyecto</label>
        <input
          id="edit-project-name"
          required
          minLength={3}
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <label htmlFor="edit-project-description">Descripción</label>
        <textarea
          id="edit-project-description"
          maxLength={300}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
        />
        {update.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(update.error)}
          </p>
        )}
        <Button type="submit" disabled={update.isPending}>
          Guardar cambios
        </Button>
      </form>
    </Dialog>
  );
}
