import re
import unicodedata
from datetime import datetime
from uuid import UUID

from dataflow.modules.understanding.semantic_contracts import (
    HINTS_VERSION,
    ColumnDraft,
    ColumnSuggestion,
    GrainDefinition,
    KeyDefinition,
    Representation,
    Review,
    ReviewState,
    SemanticColumn,
    SemanticContent,
    SemanticDraft,
    SemanticModel,
    SemanticWarning,
)
from dataflow.platform.canonical import canonical
from dataflow.platform.errors import ApplicationError

# Catálogo estático/versionado: sin inferir moneda por locale ni consultar servicios externos.
CURRENCY_CODES = frozenset(
    (
        "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV "
        "BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK "
        "DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL "
        "HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT "
        "LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR "
        "MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF "
        "SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP "
        "TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF XAG XAU "
        "XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG"
    ).split()
)


def suggestions(source: Representation) -> list[ColumnSuggestion]:
    profiles = {column.name: column for column in source.profile.columns} if source.profile else {}
    result = []
    for column in source.columns:
        profile = profiles.get(column.name)
        name = "".join(
            c
            for c in unicodedata.normalize("NFKD", column.name.casefold())
            if not unicodedata.combining(c)
        )
        role = "unknown"
        reasons = ["No hay evidencia suficiente para proponer un rol de negocio."]
        if re.search(r"(^id$|_id$|^id_|codigo|postal|identifier)", name) or (
            profile and any(re.fullmatch(r"0[0-9]+", value) for value in profile.examples)
        ):
            role, reasons = (
                "identifier",
                ["Nombre de identificador o ejemplos con ceros iniciales; requiere revisión."],
            )
        elif (profile and profile.suggested_type == "date") or re.search(r"fecha|date", name):
            role, reasons = (
                "business_date",
                ["Formato o nombre compatible con fecha; su significado debe confirmarse."],
            )
        elif re.search(
            r"importe|monto|precio|costo|total|cantidad|unidades|amount|revenue|cost", name
        ):
            role, reasons = (
                "measure",
                ["El nombre sugiere una medida. No confirma unidad, moneda ni fórmula de negocio."],
            )
        elif re.search(r"region|categoria|category|ciudad|pais|segment|estado|status", name) or (
            profile
            and source.profile
            and profile.unique_count <= min(20, source.profile.row_count // 2)
        ):
            role, reasons = (
                "dimension",
                ["Nombre/cardinalidad compatible con segmentación; requiere revisión."],
            )
        result.append(
            ColumnSuggestion(
                column_id=column.id,
                suggested_role=role,
                suggested_type=profile.suggested_type if profile else None,
                reasons=reasons,
            )
        )
    return result


def initial_draft(source: Representation) -> SemanticDraft:
    formats = {
        "integer": "integer_ascii",
        "decimal": "decimal_dot",
        "date": "iso_date",
        "boolean": "boolean_lowercase",
    }
    return SemanticDraft(
        columns=[
            ColumnDraft(
                column_id=hint.column_id,
                role=hint.suggested_role,
                interpretation_type=hint.suggested_type,
                parse_format=formats.get(hint.suggested_type or ""),
            )
            for hint in suggestions(source)
        ]
    )


def editable(content: SemanticContent) -> SemanticDraft:
    return SemanticDraft(
        dataset_description=content.dataset_description,
        row_grain={
            "description": content.row_grain.description,
            "review_state": content.row_grain.review.state,
        },
        columns=[
            ColumnDraft(
                column_id=column.id,
                description=column.description,
                interpretation_type=column.interpretation_type,
                role=column.role,
                unit=column.unit,
                currency=column.currency,
                parse_format=column.parse_format,
                null_policy=column.null_policy,
                review_state=column.review.state,
            )
            for column in content.columns
        ],
        key={
            "column_ids": content.key.column_ids,
            "null_policy": content.key.null_policy,
            "review_state": content.key.review.state,
        },
    )


def validate_draft(source: Representation, draft: SemanticDraft) -> SemanticDraft:
    ids = [column.id for column in source.columns]
    supplied = [column.column_id for column in draft.columns]
    if (
        len(set(ids)) != len(ids)
        or len(set(supplied)) != len(supplied)
        or set(ids) != set(supplied)
    ):
        raise ApplicationError(
            "SEMANTIC_COLUMNS_MISMATCH",
            "La revisión debe incluir una vez cada columna publicada.",
            422,
        )
    if len(set(draft.key.column_ids)) != len(draft.key.column_ids) or not set(
        draft.key.column_ids
    ).issubset(ids):
        raise ApplicationError(
            "SEMANTIC_KEY_INVALID", "La clave contiene columnas repetidas o inexistentes.", 422
        )
    if draft.key.review_state == "confirmed" and not draft.key.column_ids:
        raise ApplicationError(
            "SEMANTIC_KEY_REQUIRED", "Selecciona columnas para confirmar una clave.", 422
        )
    if draft.row_grain.review_state == "confirmed" and not draft.row_grain.description:
        raise ApplicationError(
            "SEMANTIC_GRAIN_REQUIRED",
            "Describe qué representa cada fila antes de confirmarlo.",
            422,
        )
    expected_format = {
        "integer": "integer_ascii",
        "decimal": "decimal_dot",
        "date": "iso_date",
        "boolean": "boolean_lowercase",
    }
    for column in draft.columns:
        if column.currency and (column.currency not in CURRENCY_CODES or column.role != "measure"):
            raise ApplicationError(
                "SEMANTIC_CURRENCY_INVALID",
                "La moneda debe ser un código del catálogo ISO 4217 y pertenecer a una medida.",
                422,
            )
        if column.unit and column.role != "measure":
            raise ApplicationError(
                "SEMANTIC_UNIT_INVALID",
                "Las unidades se declaran en columnas con rol de medida.",
                422,
            )
        if (
            column.parse_format
            and expected_format.get(column.interpretation_type or "") != column.parse_format
        ):
            raise ApplicationError(
                "SEMANTIC_FORMAT_INVALID",
                "El formato no corresponde al tipo de interpretación.",
                422,
            )
        if (column.null_policy.mode == "explicit_tokens") != bool(column.null_policy.tokens):
            raise ApplicationError(
                "SEMANTIC_NULL_POLICY_INVALID",
                "Usa tokens sólo en una política explícita y proporciona al menos uno.",
                422,
            )
    by_id = {column.column_id: column for column in draft.columns}
    return draft.model_copy(update={"columns": [by_id[id] for id in ids]})


def make_content(
    source: Representation,
    draft: SemanticDraft,
    actor: UUID,
    now: datetime,
    previous: SemanticContent | None,
) -> SemanticContent:
    defaults = initial_draft(source)
    prior = editable(previous) if previous else None

    def review(
        value: SemanticModel,
        old: SemanticModel | None,
        old_review: Review | None,
        default: SemanticModel,
        state: ReviewState,
    ) -> Review:
        def encoded(item: SemanticModel) -> str:
            return canonical(item.model_dump(mode="json"))

        if old_review and old is not None and encoded(value) == encoded(old):
            return old_review
        if state == "pending":
            heuristic = encoded(value) == encoded(default)
            return Review(
                state="pending",
                origin="heuristic" if heuristic else "user",
                actor_id=None if heuristic else actor,
                reviewed_at=None,
            )
        return Review(state=state, origin="user", actor_id=actor, reviewed_at=now)

    profile = {c.name: c for c in source.profile.columns} if source.profile else {}
    columns = []
    for index, (facts, column) in enumerate(zip(source.columns, draft.columns, strict=True)):
        prior_column = previous.columns[index] if previous else None
        columns.append(
            SemanticColumn(
                **facts.model_dump(),
                suggested_type=profile[facts.name].suggested_type
                if facts.name in profile
                else None,
                description=column.description,
                interpretation_type=column.interpretation_type,
                role=column.role,
                unit=column.unit,
                currency=column.currency,
                parse_format=column.parse_format,
                null_policy=column.null_policy,
                review=review(
                    column,
                    prior.columns[index] if prior else None,
                    prior_column.review if prior_column else None,
                    defaults.columns[index],
                    column.review_state,
                ),
            )
        )
    return SemanticContent(
        table_ref=source.table_ref,
        dataset_description=draft.dataset_description,
        suggestion_rules_version=HINTS_VERSION,
        row_grain=GrainDefinition(
            description=draft.row_grain.description,
            review=review(
                draft.row_grain,
                prior.row_grain if prior else None,
                previous.row_grain.review if previous else None,
                defaults.row_grain,
                draft.row_grain.review_state,
            ),
        ),
        columns=columns,
        key=KeyDefinition(
            column_ids=draft.key.column_ids,
            null_policy=draft.key.null_policy,
            review=review(
                draft.key,
                prior.key if prior else None,
                previous.key.review if previous else None,
                defaults.key,
                draft.key.review_state,
            ),
        ),
    )


def context_warnings(draft: SemanticDraft) -> list[SemanticWarning]:
    result = []
    if draft.row_grain.review_state != "confirmed":
        result.append(
            SemanticWarning(
                code="GRAIN_PENDING", message="Todavía no está confirmado qué representa cada fila."
            )
        )
    for column in draft.columns:
        if column.role == "measure" and not column.unit and not column.currency:
            result.append(
                SemanticWarning(
                    code="UNIT_PENDING",
                    message="Falta definir unidad o moneda de esta medida.",
                    column_id=column.column_id,
                )
            )
        if column.role == "identifier" and column.interpretation_type in {"integer", "decimal"}:
            result.append(
                SemanticWarning(
                    code="IDENTIFIER_NOT_MEASURE",
                    message="Un identificador numérico no es una medida; se conservan sus valores.",
                    column_id=column.column_id,
                )
            )
    return result
