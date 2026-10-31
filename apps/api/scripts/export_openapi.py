"""Exportar contrato sin depender de una API en ejecución ni consultar PostgreSQL."""

import argparse
import json
from pathlib import Path

from dataflow.bootstrap.app import app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
target = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "dataflow.json"
content = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
if args.check:
    if not target.exists() or target.read_text(encoding="utf-8") != content:
        raise SystemExit("Contrato desactualizado: ejecutar scripts/export_openapi.py")
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(target)
