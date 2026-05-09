"""Cloud v1 commercial permission catalog and role-permission bundles.

DESIGN
------
Permissions live in code (this module), not in the database. Reasons:
  - Permission set changes are reviewed in PRs and versioned in git.
  - No DB write can grant new privileges; privilege escalation requires
    repo write + deploy, not just SQL access.
  - Type-safe references everywhere: require_permission(Permission.DRONE_READ)
    is typo-proof; a string literal isn't.

Roles live in the database (the `roles` table) because the *grant* is
per-user-per-org and audit-tracked. The *bundle* (which permissions a role
grants) is code, not DB.

ROLE_PERMISSIONS is consulted at request time: given a Permission, find all
role names whose bundle contains it. Then check if the user has any active
grant of those roles at the target org or any ancestor (recursive CTE).

CLOUD V1 SCOPE
--------------
Cloud v1 is COMMERCIAL ONLY. Of 6 seeded roles in the database:
  - 3 are user-facing here: viewer, operator, admin
  - 2 are GCS-side personas with empty cloud bundles: planner, technician
  - 1 is Specter-internal (granted only at the Specter root org): developer

When the GCS ships, planner/technician bundles get populated.
When the military fork ships, additional permissions are added and bundled.
"""
from enum import Enum


class Permission(str, Enum):
    # ----- Customer-facing operational reads -----
    DRONE_READ = "drone:read"
    TELEMETRY_READ = "telemetry:read"
    VIDEO_READ = "video:read"
    MISSION_READ = "mission:read"

    # ----- Customer-facing operational writes -----
    MISSION_WRITE = "mission:write"
    DRONE_CONFIGURE = "drone:configure"
    """Whitelisted drone operational settings (mode, geofence, max speed).
    Defined now, not bundled in v1; ships with the drone-settings UI."""

    # ----- Customer-org admin -----
    USER_INVITE = "user:invite"
    USER_REMOVE = "user:remove"
    USER_ASSIGN_ROLE = "user:assign_role"
    ORG_SETTINGS = "org:settings"
    AUDIT_READ = "audit:read"

    # ----- Specter-org-only (no customer role bundles these) -----
    DRONE_CONFIGURE_ADVANCED = "drone:configure_advanced"
    """PID, calibration, firmware-level params. Reserved for the developer role,
    granted only at Specter root org. Routes that consume this permission ship
    when the param-tuning cloud feature lands."""

    PLATFORM_AUDIT_READ = "platform:audit_read"
    PLATFORM_ORG_MANAGE = "platform:org_manage"
    PLATFORM_DRONE_MANAGE = "platform:drone_manage"
    DEV_DEBUG = "dev:debug"


# Role -> permission bundle. Bundles can overlap (operator includes viewer's
# permissions); grants in user_roles are independent (a user with operator
# alone has full operator permissions without needing a separate viewer grant).
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "viewer": frozenset({
        Permission.DRONE_READ,
        Permission.TELEMETRY_READ,
        Permission.VIDEO_READ,
        Permission.MISSION_READ,
    }),
    "operator": frozenset({
        Permission.DRONE_READ,
        Permission.TELEMETRY_READ,
        Permission.VIDEO_READ,
        Permission.MISSION_READ,
        Permission.MISSION_WRITE,
    }),
    "admin": frozenset({
        # Operational read-through so admins can verify what their users see.
        Permission.DRONE_READ,
        Permission.TELEMETRY_READ,
        Permission.VIDEO_READ,
        Permission.MISSION_READ,
        # Org management
        Permission.USER_INVITE,
        Permission.USER_REMOVE,
        Permission.USER_ASSIGN_ROLE,
        Permission.ORG_SETTINGS,
        Permission.AUDIT_READ,
    }),
    # GCS-side personas — seeded for forward compat, no cloud bundles in v1.
    "planner": frozenset(),
    "technician": frozenset(),
    # Specter-internal — only ever granted at the Specter root org.
    "developer": frozenset({
        Permission.DRONE_READ,
        Permission.TELEMETRY_READ,
        Permission.VIDEO_READ,
        Permission.MISSION_READ,
        Permission.DRONE_CONFIGURE,
        Permission.DRONE_CONFIGURE_ADVANCED,
        Permission.PLATFORM_AUDIT_READ,
        Permission.PLATFORM_ORG_MANAGE,
        Permission.PLATFORM_DRONE_MANAGE,
        Permission.DEV_DEBUG,
    }),
}


# Roles that may ONLY be granted at the Specter root org. UI/API grant flows
# must reject attempts to grant these at customer orgs. Belt-and-suspenders to
# the `roles.is_platform_role` flag.
PLATFORM_ONLY_ROLES: frozenset[str] = frozenset({"developer"})


def roles_with_permission(permission: Permission) -> list[str]:
    """All role names whose bundle includes this permission. Used by the
    authorization check to compute the eligible-role list before the DB query.
    """
    return [name for name, perms in ROLE_PERMISSIONS.items() if permission in perms]
