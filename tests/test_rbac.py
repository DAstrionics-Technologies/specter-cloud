"""Tests for app.auth.rbac.check_permission — the recursive CTE auth check.

These tests are the heart of the security model. Every scenario the
auth check has to get right gets a named test:

  1. Self-org grant works
  2. Parent-org grant cascades to descendants
  3. Sibling org grant doesn't reach across (cross-customer isolation)
  4. Three-level chain works (Specter -> Customer -> Site)
  5. Revoked grant denies
  6. Permission with no role bundle denies
  7. Multi-grant: closest-depth match wins (operator at site beats viewer at corps)
  8. Eligible-roles filtering: irrelevant roles don't grant
  9. Inactive user not handled here — that's the dependency layer's job
"""
from datetime import datetime, timezone

from sqlalchemy import select

from app.auth.password import hash_password
from app.auth.permissions import Permission
from app.auth.rbac import check_permission
from app.models import Org, Role, User, UserRole


async def _grant(db_session, user, org, role_name):
    role = await db_session.scalar(select(Role).where(Role.name == role_name))
    db_session.add(
        UserRole(user_id=user.id, org_id=org.id, role_id=role.id)
    )
    await db_session.flush()


async def _make_user(db_session, org, email):
    u = User(
        email=email,
        password_hash=hash_password("hunter2"),
        name=email.split("@")[0],
        org_id=org.id,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# ============================================================
# Scenario 1: Self-org grant works
# ============================================================


async def test_grant_at_user_home_org_allows(db_session):
    org = Org(name="SelfCo", slug="selfco-rbac")
    db_session.add(org)
    await db_session.flush()

    user = await _make_user(db_session, org, "alice@selfco.example")
    await _grant(db_session, user, org, "operator")

    result = await check_permission(user, Permission.MISSION_WRITE, org.id, db_session)

    assert result.allowed is True
    assert result.matched_role_name == "operator"
    assert result.matched_org_id == org.id
    assert result.reason == "granted_via_operator"


# ============================================================
# Scenario 2: Parent-org grant cascades to descendants
# (This is the Specter-as-root-org pattern)
# ============================================================


async def test_grant_at_parent_org_cascades_to_child(db_session):
    """Specter staff with admin at the root org should reach customer drones."""
    specter = Org(name="Specter", slug="specter-rbac")
    db_session.add(specter)
    await db_session.flush()

    customer = Org(name="CustomerA", slug="customera-rbac", parent_org_id=specter.id)
    db_session.add(customer)
    await db_session.flush()

    staff = await _make_user(db_session, specter, "staff@specter.example")
    await _grant(db_session, staff, specter, "admin")

    # Check at the CUSTOMER org — admin grant at Specter should cascade.
    result = await check_permission(
        staff, Permission.USER_INVITE, customer.id, db_session
    )

    assert result.allowed is True
    assert result.matched_role_name == "admin"
    assert result.matched_org_id == specter.id  # matched at the parent, not the child


# ============================================================
# Scenario 3: Sibling org grant doesn't reach across
# (Cross-customer isolation)
# ============================================================


async def test_grant_at_sibling_org_denies(db_session):
    """Customer A admin must NOT reach Customer B's resources."""
    specter = Org(name="Specter", slug="specter-sib")
    db_session.add(specter)
    await db_session.flush()

    cust_a = Org(name="CustA", slug="custa-sib", parent_org_id=specter.id)
    cust_b = Org(name="CustB", slug="custb-sib", parent_org_id=specter.id)
    db_session.add_all([cust_a, cust_b])
    await db_session.flush()

    a_admin = await _make_user(db_session, cust_a, "admin@a.example")
    await _grant(db_session, a_admin, cust_a, "admin")

    # Check at Customer B — no role grant at B or any ancestor of B that
    # this user has, so denied.
    result = await check_permission(
        a_admin, Permission.USER_INVITE, cust_b.id, db_session
    )

    assert result.allowed is False
    assert result.reason == "no_matching_role_grant"


# ============================================================
# Scenario 4: Three-level chain (Specter -> Customer -> Site)
# ============================================================


async def test_grant_at_grandparent_cascades_two_levels(db_session):
    specter = Org(name="Specter", slug="specter-3lvl")
    db_session.add(specter)
    await db_session.flush()

    customer = Org(name="Cust3", slug="cust3-3lvl", parent_org_id=specter.id)
    db_session.add(customer)
    await db_session.flush()

    site = Org(name="Site3", slug="site3-3lvl", parent_org_id=customer.id)
    db_session.add(site)
    await db_session.flush()

    user = await _make_user(db_session, specter, "ground@specter.example")
    await _grant(db_session, user, specter, "developer")

    # Check at the site (grandchild) — developer at root should still match.
    result = await check_permission(
        user, Permission.DRONE_CONFIGURE_ADVANCED, site.id, db_session
    )

    assert result.allowed is True
    assert result.matched_org_id == specter.id


# ============================================================
# Scenario 5: Revoked grant denies
# ============================================================


async def test_revoked_grant_denies(db_session):
    org = Org(name="RevokeCo", slug="revokeco-rbac")
    db_session.add(org)
    await db_session.flush()

    user = await _make_user(db_session, org, "rev@example.com")
    await _grant(db_session, user, org, "operator")

    # Revoke
    grant = await db_session.scalar(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    grant.revoked_at = datetime.now(timezone.utc)
    grant.revoked_reason = "demoted"
    await db_session.flush()

    result = await check_permission(user, Permission.MISSION_WRITE, org.id, db_session)

    assert result.allowed is False
    assert result.reason == "no_matching_role_grant"


# ============================================================
# Scenario 6: Permission with no role bundle denies
# ============================================================


async def test_unbundled_permission_denies_immediately(db_session):
    """If a permission isn't in any role's bundle, the check denies without
    even hitting the DB. Defensive — catches mistakes where a route uses
    a permission that no role grants."""
    org = Org(name="UnbundledCo", slug="unbundledco-rbac")
    db_session.add(org)
    await db_session.flush()

    user = await _make_user(db_session, org, "anyone@example.com")
    await _grant(db_session, user, org, "admin")

    # DRONE_CONFIGURE is defined but not yet bundled in any role except
    # `developer`. An admin user at a regular customer org has no path to it.
    result = await check_permission(
        user, Permission.DRONE_CONFIGURE, org.id, db_session
    )

    assert result.allowed is False


# ============================================================
# Scenario 7: Closest-depth match wins
# ============================================================


async def test_closest_depth_match_wins(db_session):
    """If the user has different roles at multiple levels of the chain,
    the closest org's role is the one that matches (and gets logged)."""
    specter = Org(name="Specter", slug="specter-depth")
    db_session.add(specter)
    await db_session.flush()

    customer = Org(name="DepthCo", slug="depthco-rbac", parent_org_id=specter.id)
    db_session.add(customer)
    await db_session.flush()

    user = await _make_user(db_session, specter, "multi@specter.example")
    await _grant(db_session, user, specter, "viewer")
    await _grant(db_session, user, customer, "operator")  # closer match

    # Operator can MISSION_WRITE; viewer cannot. Customer is closer than Specter.
    result = await check_permission(
        user, Permission.MISSION_WRITE, customer.id, db_session
    )

    assert result.allowed is True
    assert result.matched_role_name == "operator"
    assert result.matched_org_id == customer.id  # the closer match, not parent


# ============================================================
# Scenario 8: Eligible-roles filtering
# ============================================================


async def test_irrelevant_role_does_not_grant(db_session):
    """A user with planner (no cloud bundle in v1) must not get any
    cloud permissions just because the role exists."""
    org = Org(name="PlannerCo", slug="plannerco-rbac")
    db_session.add(org)
    await db_session.flush()

    user = await _make_user(db_session, org, "planner@example.com")
    await _grant(db_session, user, org, "planner")  # empty bundle in cloud v1

    result = await check_permission(user, Permission.DRONE_READ, org.id, db_session)
    assert result.allowed is False


async def test_unrelated_user_denies(db_session):
    """A different user with the same role at the same org doesn't grant
    THIS user anything. Per-user grant scoping is honored."""
    org = Org(name="ScopeCo", slug="scopeco-rbac")
    db_session.add(org)
    await db_session.flush()

    granted = await _make_user(db_session, org, "granted@example.com")
    await _grant(db_session, granted, org, "operator")

    other = await _make_user(db_session, org, "other@example.com")
    # No grant for `other`

    result = await check_permission(
        other, Permission.MISSION_WRITE, org.id, db_session
    )

    assert result.allowed is False


# ============================================================
# Result provenance (used by audit log)
# ============================================================


async def test_allowed_result_carries_role_and_org_for_audit(db_session):
    """The PermissionCheckResult fields drive the audit log row. Verify
    they're populated correctly on allow."""
    org = Org(name="ProvCo", slug="provco-rbac")
    db_session.add(org)
    await db_session.flush()

    user = await _make_user(db_session, org, "prov@example.com")
    await _grant(db_session, user, org, "viewer")

    result = await check_permission(user, Permission.DRONE_READ, org.id, db_session)

    viewer_role = await db_session.scalar(select(Role).where(Role.name == "viewer"))
    assert result.matched_role_id == viewer_role.id
    assert result.matched_org_id == org.id
    assert result.matched_role_name == "viewer"
    assert result.reason == "granted_via_viewer"


async def test_denied_result_has_null_match_fields(db_session):
    """On deny, no match fields are set — the audit row will record NULLs."""
    org = Org(name="NoneCo", slug="noneco-rbac")
    db_session.add(org)
    await db_session.flush()

    user = await _make_user(db_session, org, "none@example.com")
    # No grant at all

    result = await check_permission(user, Permission.DRONE_READ, org.id, db_session)
    assert result.allowed is False
    assert result.matched_role_id is None
    assert result.matched_org_id is None
    assert result.matched_role_name is None
