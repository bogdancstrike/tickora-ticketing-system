"""Pydantic input schemas for ticket endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, IPvAnyAddress

PRIORITY = Literal["low", "medium", "high", "critical"]


class CreateTicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beneficiary_type: Literal["internal", "external"]

    # External-only requester fields (optional for internal — derived from the user)
    requester_first_name:  str | None = Field(default=None, max_length=255)
    requester_last_name:   str | None = Field(default=None, max_length=255)
    requester_email:       EmailStr | None = None
    requester_phone:       str | None = Field(default=None, max_length=50)
    organization_name:     str | None = Field(default=None, max_length=255)
    external_identifier:   str | None = Field(default=None, max_length=255)

    requester_ip:          IPvAnyAddress | None = None

    title:                 str | None = Field(default=None, max_length=500)
    txt:                   str        = Field(min_length=5, max_length=20000)


class ListTicketsQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status:               str | list[str] | None = None
    priority:             str | list[str] | None = None
    category:             str | None = None
    beneficiary_type:     Literal["internal", "external"] | None = None
    assignee_user_id:     str | None = None
    current_sector_code:  str | None = None
    created_after:        datetime | None = None
    created_before:       datetime | None = None
    ticket_code:          str | None = None
    search:               str | None = Field(default=None, max_length=200)
    sort_by:              Literal[
        "created_at", "updated_at", "ticket_code", "priority", "status", "title"
    ] | None = None
    sort_dir:             Literal["asc", "desc"] | None = None
    cursor:               str | None = None
    limit:                int | None = Field(default=None, ge=1, le=200)
