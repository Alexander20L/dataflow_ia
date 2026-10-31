from pydantic import BaseModel


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    correlation_id: str
    details: list[ErrorDetail] | None = None
