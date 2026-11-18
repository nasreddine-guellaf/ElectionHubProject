from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, model_validator

from app.domain_schemas import Code, ExpectedVersion, Input, Name, Read

Role = Literal["ADMIN", "AGENT", "VALIDATOR", "CITIZEN"]
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, pattern=r"^demo-[a-z0-9_.-]+$", max_length=80
    ),
]
Password = Annotated[SecretStr, Field(min_length=12, max_length=128)]


class LoginInput(Input):
    username: Username
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class TokenRead(Read):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class AccountInput(Input):
    code: Code
    display_name: Name
    username: Username
    password: Password
    role: Literal["ADMIN", "AGENT", "VALIDATOR"]


class AccountUpdate(Input):
    role: Literal["ADMIN", "AGENT", "VALIDATOR"]
    active: bool


class PasswordChange(Input):
    current_password: Annotated[SecretStr, Field(min_length=1, max_length=128)]
    new_password: Password


class PasswordReset(Input):
    new_password: Password


class Profile(Read):
    id: UUID
    display_name: str
    role: Role


class AccountRead(Profile):
    username: str
    active: bool


class AuditRead(Read):
    id: UUID
    actor_id: UUID | None
    target_id: UUID | None
    action: str
    resource: str | None
    created_at: datetime


class DecisionInput(ExpectedVersion):
    decision: Literal["APPROVED", "REJECTED"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""

    @model_validator(mode="after")
    def rejection_reason(self):
        if self.decision == "REJECTED" and not self.reason:
            raise ValueError("Le rejet exige un motif.")
        return self


class OtpRequest(Input):
    cin: Annotated[str, StringConstraints(pattern=r"^DEMO-CIN-[A-Z0-9-]+$", max_length=50)]


class OtpRequested(Read):
    challenge_id: UUID
    message: str = (
        "Si cette référence fictive est connue, un code a été envoyé au simulateur local."
    )


class OtpVerify(Input):
    challenge_id: UUID
    code: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
