"""Procedencia de los artefactos de una carga (Fase 23).

Una carga publica en una sola ejecución su tabla leída, su perfil, su calidad y su análisis. Una
versión derivada por textos declarados como nulos los reparte en dos: la tabla sale de la
ejecución `null_cleaning` y el resto del análisis de esa tabla (`table_analysis`). Los trabajos de
fondo comprueban que lo que reciben es de la misma carga con esta regla.
"""

from uuid import UUID

from dataflow.modules.executions.public import Artifact, Executions


def same_load(executions: Executions, owner: UUID, produced: Artifact, table: Artifact) -> bool:
    """`produced` (perfil, calidad o análisis) se calculó sobre `table`: en la misma ejecución, o
    en el análisis de una versión derivada cuya entrada fijada es exactamente esa tabla."""
    if produced.execution_id == table.execution_id:
        return True
    run = executions.get(owner, produced.execution_id)
    return (
        run.kind == "table_analysis"
        and run.input_artifact_id == table.id
        and run.input_artifact_sha256 == table.content.sha256
    )
