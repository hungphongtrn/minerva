"""Guest identity generation for anonymous requests.

Provides ephemeral principal generation for requests without explicit
user authentication. Guest identities are cryptographically strong random
IDs that do not persist to the database.
"""

import secrets
from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class GuestPrincipal:
    """Ephemeral principal for guest/anonymous requests.

    Guest principals are generated on-the-fly for each request and never
    persist to the database. They represent anonymous users and cannot
    access workspace-scoped resources that require authentication.
    """

    workspace_id: Optional[str] = None
    key_id: str = "guest"
    scopes: List[str] = None
    is_active: bool = True
    is_guest: bool = True
    guest_id: str = ""

    def __post_init__(self):
        # Ensure scopes is a list
        if self.scopes is None:
            object.__setattr__(self, "scopes", [])


def create_guest_principal() -> GuestPrincipal:
    """Generate a new ephemeral guest principal.

    Creates a cryptographically strong random identifier for the guest
    that is unique to this request. The guest ID has no associated
    workspace or persisted state.

    Returns:
        GuestPrincipal with random ID and guest flag set
    """
    # Generate a cryptographically strong random guest ID
    # Using secrets module (same source as API keys for consistency)
    guest_id = f"guest_{secrets.token_urlsafe(24)}"

    return GuestPrincipal(
        workspace_id=None,
        key_id="guest",
        scopes=[],  # Guests have no scopes by default
        is_active=True,
        is_guest=True,
        guest_id=guest_id,
    )


def is_guest_principal(principal) -> bool:
    """Check if a principal is a guest principal.

    Args:
        principal: Any principal object (GuestPrincipal or Principal)

    Returns:
        True if the principal represents a guest, False otherwise
    """
    if principal is None:
        return True
    return getattr(principal, "is_guest", False)
