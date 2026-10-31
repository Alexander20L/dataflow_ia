from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from dataflow.bootstrap.dependencies import CurrentIdentity, Identity
from dataflow.modules.identity.application import IssuedSession
from dataflow.modules.identity.contracts import SessionIdentity
from dataflow.platform.config import get_settings
from dataflow.platform.errors import ApplicationError

router = APIRouter(prefix="/api/v1/auth", tags=["Identity"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(LoginRequest):
    name: str = Field(min_length=2, max_length=80, pattern=r"\S")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    name: str


class SessionResponse(BaseModel):
    user: UserResponse
    csrf_token: str
    expires_at: datetime


def session_response(identity: SessionIdentity) -> SessionResponse:
    return SessionResponse(
        user=UserResponse.model_validate(identity.user),
        csrf_token=identity.csrf_token,
        expires_at=identity.expires_at,
    )


def issue_cookie(response: Response, issued: IssuedSession) -> SessionResponse:
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        issued.token,
        max_age=settings.session_hours * 3600,
        path="/api/v1",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return session_response(issued.identity)


@router.post("/register", response_model=SessionResponse, status_code=201, operation_id="register")
def register(
    body: RegisterRequest, request: Request, response: Response, service: Identity
) -> SessionResponse:
    if not get_settings().registration_enabled:
        raise ApplicationError("REGISTRATION_DISABLED", "El registro no está habilitado.", 403)
    issued = service.authenticate(
        str(body.email),
        body.password,
        request.client.host if request.client else "unknown",
        body.name,
    )
    return issue_cookie(response, issued)


@router.post("/login", response_model=SessionResponse, operation_id="login")
def login(
    body: LoginRequest, request: Request, response: Response, service: Identity
) -> SessionResponse:
    issued = service.authenticate(
        str(body.email), body.password, request.client.host if request.client else "unknown"
    )
    return issue_cookie(response, issued)


@router.get("/me", response_model=SessionResponse, operation_id="getSession")
def me(identity: CurrentIdentity) -> SessionResponse:
    return session_response(identity)


@router.post("/logout", status_code=204, operation_id="logout")
def logout(identity: CurrentIdentity, service: Identity) -> Response:
    service.logout(identity)
    response = Response(status_code=204)
    response.delete_cookie(
        get_settings().cookie_name,
        path="/api/v1",
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
    )
    return response
