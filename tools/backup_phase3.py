"""Copia coordinada 0003 antes de la migración semántica 0004. Sólo host local."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime

from backup_phase2 import COMPOSE, ROOT, checksum, run


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true", required=True)
    args = parser.parse_args()
    assert args.stop

    def sql(query: str) -> str:
        return run(
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
                query,
            ]
        )

    if sql("SELECT version_num FROM alembic_version") != "0003":
        raise RuntimeError("Herramienta exclusiva del corte desde 0003.")
    pending = "SELECT count(*) FROM execution_runs WHERE state IN ('queued','running')"
    if int(sql(pending)):
        raise RuntimeError("Espera a que terminen los trabajos antes de respaldar.")
    container = run(COMPOSE + ["ps", "-a", "-q", "api"])
    config = json.loads(
        run(["docker", "inspect", "--format", "{{json .Config}}", container])
    )
    previous = run(["docker", "inspect", "--format", "{{.Image}}", container])
    mounts = json.loads(
        run(["docker", "inspect", "--format", "{{json .Mounts}}", container])
    )
    volume = next(
        m["Name"]
        for m in mounts
        if m.get("Destination") == "/app/.data/objects" and m.get("Type") == "volume"
    )
    run(COMPOSE + ["stop", "web", "api", "worker"])
    if int(sql(pending)):
        raise RuntimeError(
            "Entró un trabajo durante la pausa; deja drenar el worker anterior."
        )
    directory = (
        ROOT
        / ".data/backups"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-phase3")
    )
    directory.mkdir(parents=True, exist_ok=False)
    dump, archive, rootfs = (
        directory / "database.dump",
        directory / "objects.tar.gz",
        directory / "previous-api-rootfs.tar",
    )
    run(
        COMPOSE
        + [
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "dataflow",
            "-d",
            "dataflow",
            "-Fc",
        ],
        dump,
    )
    run(["docker", "export", container], rootfs)
    code = (
        "import sys,tarfile;"
        "t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz');"
        "t.add('/objects',arcname='objects');"
        "t.close()"
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
            "dataflow-api:latest",
            "-c",
            code,
        ],
        archive,
    )
    objects = json.loads(
        sql(
            "SELECT COALESCE(json_agg(t),'[]'::json) FROM ("
            "SELECT id::text AS object_id, sha256, byte_size "
            "FROM dataset_objects ORDER BY id) t"
        )
    )
    counts = json.loads(
        sql(
            "SELECT json_build_object("
            "'versions',(SELECT count(*) FROM dataset_version_records),"
            "'executions',(SELECT count(*) FROM execution_runs),"
            "'artifacts',(SELECT count(*) FROM execution_artifacts),"
            "'plans',(SELECT count(*) FROM execution_plan_revisions))"
        )
    )
    identity = hashlib.sha256(
        (
            "dataflow:release_inventory:v1\n"
            + json.dumps(objects, sort_keys=True, separators=(",", ":"))
        ).encode()
    ).hexdigest()
    manifest = {
        "source_revision": "0003",
        "created_at": datetime.now(UTC).isoformat(),
        "database_sha256": checksum(dump),
        "objects_sha256": checksum(archive),
        "previous_api_rootfs_sha256": checksum(rootfs),
        "previous_api_image": previous,
        "previous_api_config": {
            key: config.get(key) for key in ["WorkingDir", "User", "Cmd"]
        },
        "inventory": {**counts, "objects": len(objects), "identity_sha256": identity},
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(directory)
    print(
        "Copia Fase 3 completada; PostgreSQL activo y servicios de escritura pausados."
    )


if __name__ == "__main__":
    main()
