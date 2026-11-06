"""Proceso aislado de reports.render_pdf@1: instantánea del informe → PDF. Sin base de datos."""

import argparse
import json
from pathlib import Path

from dataflow.modules.reports.contracts import ReportSnapshot
from dataflow.modules.reports.pdf import render_pdf
from dataflow.platform.errors import ApplicationError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        snapshot = ReportSnapshot.model_validate_json(args.input.read_bytes())
        (args.output / "report.pdf").write_bytes(render_pdf(snapshot))
    except ApplicationError as exc:
        (args.output / "error.json").write_text(
            json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=False),
            encoding="utf-8",
        )
        raise SystemExit(2) from None
    except Exception:
        (args.output / "error.json").write_text(
            json.dumps({"code": "PROCESSING_ERROR", "message": "No se pudo generar el PDF."}),
            encoding="utf-8",
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
