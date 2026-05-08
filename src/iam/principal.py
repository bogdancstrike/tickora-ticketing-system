"""The Principal — what every authorized handler receives.

Decoupled from Keycloak claims so callers can build one in tests cheaply.
"""
from dataclasses import dataclass, field
from typing import Iterable

# Global Keycloak realm roles Tickora cares about.
ROLE_ADMIN          = "tickora_admin"
ROLE_AUDITOR        = "tickora_auditor"
ROLE_DISTRIBUTOR    = "tickora_distributor"
ROLE_INTERNAL_USER  = "tickora_internal_user"
ROLE_EXTERNAL_USER  = "tickora_external_user"
ROLE_SECTOR_MEMBER  = "tickora_sector_member"
ROLE_SECTOR_CHIEF   = "tickora_sector_chief"
ROLE_SERVICE        = "tickora_service_account"


@dataclass(frozen=True)
class SectorMembership:
    sector_code: str
    role: str  # "member" | "chief"


@dataclass(frozen=True)
class Principal:
    user_id: str                                   # Tickora users.id (UUID str)
    keycloak_subject: str
    username: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    user_type: str = "internal"                    # "internal" | "external"
    global_roles: frozenset[str] = field(default_factory=frozenset)
    sector_memberships: tuple[SectorMembership, ...] = ()

    # ── Role helpers ───────────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:        return ROLE_ADMIN       in self.global_roles
    @property
    def is_auditor(self) -> bool:      return ROLE_AUDITOR     in self.global_roles
    @property
    def is_distributor(self) -> bool:  return ROLE_DISTRIBUTOR in self.global_roles
    @property
    def is_internal(self) -> bool:     return self.user_type   == "internal"
    @property
    def is_external(self) -> bool:     return self.user_type   == "external"

    def has_role(self, role: str) -> bool:
        return role in self.global_roles

    def has_any(self, roles: Iterable[str]) -> bool:
        roles = set(roles)
        return any(r in roles for r in self.global_roles)

    # ── Sector helpers ─────────────────────────────────────────────────────
    def is_member_of(self, sector_code: str) -> bool:
        return any(m.sector_code == sector_code and m.role == "member" for m in self.sector_memberships)

    def is_chief_of(self, sector_code: str) -> bool:
        return any(m.sector_code == sector_code and m.role == "chief" for m in self.sector_memberships)

    def is_in_sector(self, sector_code: str) -> bool:
        return any(m.sector_code == sector_code for m in self.sector_memberships)

    @property
    def member_sectors(self) -> set[str]:
        return {m.sector_code for m in self.sector_memberships if m.role == "member"}

    @property
    def chief_sectors(self) -> set[str]:
        return {m.sector_code for m in self.sector_memberships if m.role == "chief"}

    @property
    def all_sectors(self) -> set[str]:
        return {m.sector_code for m in self.sector_memberships}
