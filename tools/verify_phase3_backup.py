"""Restaurar y verificar 0003 → 0004 en recursos temporales, nunca en los originales."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from backup_phase2 import COMPOSE, checksum, run


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_revision"] == "0003"
    for name, key in [
        ("database.dump", "database_sha256"),
        ("objects.tar.gz", "objects_sha256"),
        ("previous-api-rootfs.tar", "previous_api_rootfs_sha256"),
    ]:
        assert checksum(directory / name) == manifest[key]
    token = uuid4().hex
    database, volume, dump = (
        "verify_semantic_" + token,
        "dataflow_verify_" + token,
        "/tmp/verify_" + token + ".dump",
    )
    postgres = run(COMPOSE + ["ps", "-q", "postgres"])
    image = run(
        ["docker", "image", "inspect", "dataflow-api:latest", "--format", "{{.Id}}"]
    )
    mounts = [
        "--mount",
        f"type=volume,source={volume},target=/restore",
        "--mount",
        f"type=bind,source={directory},target=/backup,readonly",
    ]
    db_created = vol_created = False
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
        db_created = True
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
        vol_created = True
        code = (
            "import tarfile;"
            "t=tarfile.open('/backup/objects.tar.gz');"
            "t.extractall('/restore',filter='data');"
            "t.close()"
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
                image,
                "-c",
                code,
            ]
        )
        password = run(
            COMPOSE + ["exec", "-T", "postgres", "printenv", "POSTGRES_PASSWORD"]
        )
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
                image,
                "sh",
                "-c",
                "alembic upgrade head && python scripts/verify_release.py --expect-no-semantics",
            ]
        )
        actual = json.loads(output.splitlines()[-1])
        assert actual["inventory"] == manifest["inventory"]
        (directory / "restore-verification.json").write_text(
            json.dumps(
                {
                    "verified": True,
                    "image_digest": image,
                    "inventory": actual["inventory"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            "Restauración 0003 → 0004 verificada: mismos datos/artefactos "
            "y cero confirmaciones inventadas."
        )
    finally:
        if db_created:
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
        if vol_created:
            run(["docker", "volume", "rm", volume])
        run(["docker", "exec", postgres, "rm", "-f", dump])


if __name__ == "__main__":
    main()
