import argparse
import json

from dataflow.bootstrap import models  # noqa: F401
from dataflow.bootstrap.cutover import cutover
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings
from dataflow.platform.database import session_factory

parser = argparse.ArgumentParser(
    description="Verificar/copiar historia 0.3 sin reescribir archivos."
)
parser.add_argument(
    "--apply", action="store_true", help="Confirmar copia y activar el recorrido nuevo."
)
args = parser.parse_args()
with session_factory() as db:
    manifest = cutover(db, LocalObjects(get_settings().storage_path), apply=args.apply)
print(json.dumps({"applied": args.apply, **manifest}, ensure_ascii=False))
