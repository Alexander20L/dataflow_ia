"""Copia coordinada antes del corte. Ejecutar en el host, con Docker Desktop."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infrastructure/compose/compose.yaml")]


def run(args: list[str], target: Path | None = None) -> str:
    if target:
        with target.open("xb") as output:
            result = subprocess.run(args, cwd=ROOT, stdout=output, stderr=subprocess.PIPE)
        text = ""
    else:
        result = subprocess.run(args, cwd=ROOT, capture_output=True)
        text = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return text.strip()


def checksum(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stop",
        action="store_true",
        required=True,
        help="Pausar API, worker y web para copiar metadatos/objetos coherentes.",
    )
    parser.add_argument(
        "--reader-image",
        default="dataflow-api:latest",
        help="Imagen con Python para leer el volumen; puede ser la imagen nueva.",
    )
    args = parser.parse_args()
    assert args.stop
    revision = run(
        COMPOSE
        + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dataflow",
            "-d",
            "dataflow",
            "-At",
            "-c",
            "SELECT version_num FROM alembic_version",
        ]
    )
    if revision != "0002":
        raise RuntimeError(
            "Herramienta exclusiva del corte desde 0002; no es un backup genérico posterior."
        )
    pending = run(
        COMPOSE
        + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dataflow",
            "-d",
            "dataflow",
            "-At",
            "-c",
            "SELECT count(*) FROM import_executions WHERE state IN ('queued','processing')",
        ]
    )
    if int(pending):
        raise RuntimeError(
            "Hay trabajos 0.3 activos. Deja que terminen antes de pausar los servicios."
        )
    container = run(COMPOSE + ["ps", "-a", "-q", "api"])
    image = run(["docker", "inspect", "--format", "{{.Image}}", container])
    previous_config = json.loads(
        run(["docker", "inspect", "--format", "{{json .Config}}", container])
    )
    mounts = json.loads(run(["docker", "inspect", "--format", "{{json .Mounts}}", container]))
    volume = next(
        m["Name"]
        for m in mounts
        if m.get("Destination") == "/app/.data/objects" and m.get("Type") == "volume"
    )
    run(COMPOSE + ["stop", "web", "api", "worker"])
    pending = run(
        COMPOSE
        + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dataflow",
            "-d",
            "dataflow",
            "-At",
            "-c",
            "SELECT count(*) FROM import_executions WHERE state IN ('queued','processing')",
        ]
    )
    if int(pending):
        raise RuntimeError(
            "Entró un trabajo durante la pausa. Reinicia el worker antiguo, deja drenar y repite."
        )
    directory = ROOT / ".data" / "backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=False)
    database, objects = directory / "database.dump", directory / "objects.tar.gz"
    previous_rootfs = directory / "previous-api-rootfs.tar"
    run(["docker", "export", container], previous_rootfs)
    run(
        COMPOSE + ["exec", "-T", "postgres", "pg_dump", "-U", "dataflow", "-d", "dataflow", "-Fc"],
        database,
    )
    code = (
        "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); "
        "t.add('/objects',arcname='objects'); t.close()"
    )
    run(
        [
            "docker",
            "run",
            "--rm",
            "--mount",
            f"type=volume,source={volume},target=/objects,readonly",
            "--entrypoint",
            "python",
            args.reader_image,
            "-c",
            code,
        ],
        objects,
    )
    inventory_sql = """
    SELECT json_build_object(
      'versions', COALESCE((SELECT json_agg(t) FROM
        (SELECT id::text AS version_id, sha256, byte_size
         FROM dataset_versions ORDER BY id) t), '[]'::json),
      'artifacts', COALESCE((SELECT json_agg(t) FROM
        (SELECT id::text AS artifact_id, sha256, byte_size
         FROM analysis_artifacts ORDER BY id) t), '[]'::json),
      'runs', (SELECT count(*) FROM import_executions));
    """
    inventory = json.loads(
        run(
            COMPOSE
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "dataflow",
                "-d",
                "dataflow",
                "-At",
                "-c",
                inventory_sql,
            ]
        )
    )
    identities = inventory["versions"] + inventory["artifacts"]
    canonical = json.dumps(identities, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "database": "dataflow",
        "source_revision": revision,
        "previous_api_image": image,
        "previous_api_rootfs_sha256": checksum(previous_rootfs),
        "previous_api_config": {
            key: previous_config.get(key) for key in ["WorkingDir", "User", "Cmd"]
        },
        "objects_volume": volume,
        "database_sha256": checksum(database),
        "objects_sha256": checksum(objects),
        "legacy_versions": len(inventory["versions"]),
        "legacy_executions": inventory["runs"],
        "legacy_artifacts": len(inventory["artifacts"]),
        "identity_sha256": hashlib.sha256(
            ("dataflow:migration:v1\n" + canonical).encode()
        ).hexdigest(),
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(directory)
    print(
        "Copia coordinada completada. Servicios de escritura pausados; PostgreSQL continúa activo."
    )


if __name__ == "__main__":
    main()
