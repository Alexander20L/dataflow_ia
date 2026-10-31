"""Restauración aislada y ensayo de cutover. No escribe en la base/volumen de usuario."""

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from backup_phase2 import COMPOSE, checksum, run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--image", default="dataflow-api:latest", help="Imagen Fase 2 ya construida."
    )
    args = parser.parse_args()
    directory = args.directory.resolve()
    verified_image = run(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_revision"] == "0002"
    assert checksum(directory / "database.dump") == manifest["database_sha256"]
    assert checksum(directory / "objects.tar.gz") == manifest["objects_sha256"]
    assert checksum(directory / "previous-api-rootfs.tar") == manifest["previous_api_rootfs_sha256"]
    token = uuid4().hex
    database, volume, dump = (
        "verify_phase2_" + token,
        "dataflow_verify_" + token,
        "/tmp/verify_" + token + ".dump",
    )
    postgres = run(COMPOSE + ["ps", "-q", "postgres"])
    mounts = [
        "--mount",
        f"type=volume,source={volume},target=/restore",
        "--mount",
        f"type=bind,source={directory},target=/backup,readonly",
    ]
    created_database = created_volume = False
    try:
        run(["docker", "cp", str(directory / "database.dump"), f"{postgres}:{dump}"])
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
                "postgres",
                "-c",
                f'CREATE DATABASE "{database}"',
            ]
        )
        created_database = True
        run(
            COMPOSE
            + [
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "-U",
                "dataflow",
                "--exit-on-error",
                "-d",
                database,
                dump,
            ]
        )
        run(["docker", "volume", "create", volume])
        created_volume = True
        extract = (
            "import tarfile; t=tarfile.open('/backup/objects.tar.gz'); "
            "t.extractall('/restore',filter='data'); t.close()"
        )
        run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "0",
                *mounts,
                "--entrypoint",
                "python",
                args.image,
                "-c",
                extract,
            ]
        )
        password = run(COMPOSE + ["exec", "-T", "postgres", "printenv", "POSTGRES_PASSWORD"])
        url = f"postgresql+psycopg://dataflow:{quote(password, safe='')}@postgres:5432/{database}"
        output = run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "dataflow_default",
                *mounts,
                "-e",
                f"DATAFLOW_DATABASE_URL={url}",
                "-e",
                "DATAFLOW_STORAGE_PATH=/restore/objects",
                args.image,
                "sh",
                "-c",
                "alembic upgrade head && python scripts/cutover.py --apply",
            ]
        )
        result = json.loads(output.splitlines()[-1])
        for key in ["legacy_versions", "legacy_executions", "legacy_artifacts", "identity_sha256"]:
            assert result[key] == manifest[key], key
        (directory / "restore-verification.json").write_text(
            json.dumps(
                {
                    "verified": True,
                    "image": args.image,
                    "image_digest": verified_image,
                    "manifest": result,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print("Restauración aislada y cutover verificados: conteos, IDs y hashes coinciden.")
    finally:
        if created_database:
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
                    "postgres",
                    "-c",
                    f'DROP DATABASE "{database}" WITH (FORCE)',
                ]
            )
        if created_volume:
            run(["docker", "volume", "rm", volume])
        run(["docker", "exec", postgres, "rm", "-f", dump])


if __name__ == "__main__":
    main()
