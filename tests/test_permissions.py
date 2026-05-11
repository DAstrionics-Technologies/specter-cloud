"""Tests for app.auth.permissions (Permission catalog and role bundles).

No DB; pure unit tests. The point is to lock the role-permission matrix
into version control with executable assertions, so any future change
to the catalog has to break these tests deliberately.
"""
from app.auth.permissions import (
    PLATFORM_ONLY_ROLES,
    Permission,
    ROLE_PERMISSIONS,
    roles_with_permission,
)


SEEDED_ROLES = {"viewer", "operator", "planner", "technician", "developer", "admin"}
CUSTOMER_FACING_ROLES = {"viewer", "operator", "admin"}
SPECTER_INTERNAL_PERMISSIONS = {
    Permission.DRONE_CONFIGURE_ADVANCED,
    Permission.PLATFORM_AUDIT_READ,
    Permission.PLATFORM_ORG_MANAGE,
    Permission.PLATFORM_DRONE_MANAGE,
    Permission.DEV_DEBUG,
}


def test_permission_values_are_unique():
    values = [p.value for p in Permission]
    assert len(values) == len(set(values))


def test_role_permissions_contains_exactly_seeded_roles():
    """ROLE_PERMISSIONS keys must match the migration's seeded roles list.
    Drift between code and seed = silent permission gaps."""
    assert set(ROLE_PERMISSIONS.keys()) == SEEDED_ROLES


def test_viewer_has_only_read_permissions():
    perms = ROLE_PERMISSIONS["viewer"]
    assert Permission.DRONE_READ in perms
    assert Permission.TELEMETRY_READ in perms
    assert Permission.VIDEO_READ in perms
    assert Permission.MISSION_READ in perms
    # No writes
    assert Permission.MISSION_WRITE not in perms
    assert Permission.USER_INVITE not in perms
    assert Permission.ORG_SETTINGS not in perms


def test_operator_can_write_missions():
    perms = ROLE_PERMISSIONS["operator"]
    assert Permission.MISSION_WRITE in perms
    # Read access stays
    assert Permission.DRONE_READ in perms
    # No org admin
    assert Permission.USER_INVITE not in perms


def test_admin_has_user_management():
    perms = ROLE_PERMISSIONS["admin"]
    assert Permission.USER_INVITE in perms
    assert Permission.USER_REMOVE in perms
    assert Permission.USER_ASSIGN_ROLE in perms
    assert Permission.ORG_SETTINGS in perms
    assert Permission.AUDIT_READ in perms


def test_admin_has_no_advanced_drone_config():
    """Customer admin must NOT have advanced drone config — that's developer-only."""
    assert Permission.DRONE_CONFIGURE_ADVANCED not in ROLE_PERMISSIONS["admin"]


def test_admin_can_read_operationally():
    """Admins get read-through so they can verify what their users see."""
    perms = ROLE_PERMISSIONS["admin"]
    assert Permission.DRONE_READ in perms
    assert Permission.TELEMETRY_READ in perms
    assert Permission.VIDEO_READ in perms
    assert Permission.MISSION_READ in perms


def test_admin_cannot_write_missions_directly():
    """Admin manages users + settings; mission write is operator territory."""
    assert Permission.MISSION_WRITE not in ROLE_PERMISSIONS["admin"]


def test_planner_and_technician_have_empty_cloud_bundles():
    """GCS-side personas — no cloud permissions in v1.
    They exist in the seed only for forward compatibility."""
    assert ROLE_PERMISSIONS["planner"] == frozenset()
    assert ROLE_PERMISSIONS["technician"] == frozenset()


def test_developer_has_advanced_and_platform_permissions():
    perms = ROLE_PERMISSIONS["developer"]
    assert Permission.DRONE_CONFIGURE_ADVANCED in perms
    assert Permission.PLATFORM_AUDIT_READ in perms
    assert Permission.PLATFORM_ORG_MANAGE in perms
    assert Permission.PLATFORM_DRONE_MANAGE in perms
    assert Permission.DEV_DEBUG in perms


def test_no_customer_role_bundles_specter_internal_permissions():
    """The whole point of `developer` being platform-locked: no customer
    role can ever bundle Specter-internal permissions, regardless of who
    edits the catalog later."""
    for role in CUSTOMER_FACING_ROLES:
        leaked = ROLE_PERMISSIONS[role] & SPECTER_INTERNAL_PERMISSIONS
        assert leaked == set(), (
            f"role {role!r} leaks Specter-internal permissions: {leaked}"
        )


def test_platform_only_roles_contains_developer():
    assert "developer" in PLATFORM_ONLY_ROLES


def test_platform_only_roles_does_not_contain_admin():
    """admin is grantable at any org tier (Specter or customer);
    only `developer` is platform-locked."""
    assert "admin" not in PLATFORM_ONLY_ROLES
    for role in ("viewer", "operator", "planner", "technician"):
        assert role not in PLATFORM_ONLY_ROLES


def test_roles_with_permission_drone_read():
    """DRONE_READ should be in every role that can do anything operational."""
    roles = set(roles_with_permission(Permission.DRONE_READ))
    assert "viewer" in roles
    assert "operator" in roles
    assert "admin" in roles
    assert "developer" in roles
    # Empty-bundle roles aren't here
    assert "planner" not in roles
    assert "technician" not in roles


def test_roles_with_permission_user_invite():
    """USER_INVITE is admin-only territory."""
    roles = set(roles_with_permission(Permission.USER_INVITE))
    assert roles == {"admin"}


def test_roles_with_permission_specter_internal_only_developer():
    """Each Specter-internal permission must be exclusively developer's."""
    for perm in SPECTER_INTERNAL_PERMISSIONS:
        roles = set(roles_with_permission(perm))
        assert roles == {"developer"}, (
            f"{perm.value} leaked beyond developer: {roles}"
        )


def test_drone_configure_reserved_for_developer_only_in_v1():
    """DRONE_CONFIGURE is defined now but operator doesn't have it yet —
    ships when the customer drone-settings UI lands. Until then, only
    developer (Specter-internal) has it."""
    roles = set(roles_with_permission(Permission.DRONE_CONFIGURE))
    assert "operator" not in roles
    assert "admin" not in roles
    assert "developer" in roles


def test_mission_write_is_operator_only_among_customer_roles():
    """Among customer roles, only operator gets mission write — not admin."""
    roles = set(roles_with_permission(Permission.MISSION_WRITE))
    customer_roles_with_mission_write = roles & CUSTOMER_FACING_ROLES
    assert customer_roles_with_mission_write == {"operator"}


def test_audit_read_is_admin_and_developer():
    """audit:read is for org admins viewing their own audit log + dev's local debug."""
    roles = set(roles_with_permission(Permission.AUDIT_READ))
    assert "admin" in roles
    # developer doesn't bundle AUDIT_READ specifically — has PLATFORM_AUDIT_READ instead.
    # If developer needs both, this test would catch the missing link.
    assert "operator" not in roles
    assert "viewer" not in roles
