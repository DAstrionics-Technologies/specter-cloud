"""Tests for the parent_org_id self-FK on the orgs table.

The recursive CTE auth check (Phase 1) walks this hierarchy. These tests
exercise the schema-level guarantees: insert valid hierarchies, reject
invalid ones, support the depth needed for real customer + Specter root
patterns.
"""
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Org


async def test_root_org_has_null_parent(db_session):
    root = Org(name="Root", slug="root", parent_org_id=None)
    db_session.add(root)
    await db_session.flush()
    assert root.parent_org_id is None


async def test_child_org_references_parent(db_session):
    parent = Org(name="Parent Corp", slug="parent")
    db_session.add(parent)
    await db_session.flush()

    child = Org(name="Subsidiary", slug="sub", parent_org_id=parent.id)
    db_session.add(child)
    await db_session.flush()
    assert child.parent_org_id == parent.id


async def test_three_level_chain(db_session):
    """Specter → Customer → Customer Site is a real expected hierarchy."""
    grandparent = Org(name="Specter", slug="specter")
    db_session.add(grandparent)
    await db_session.flush()

    parent = Org(name="Customer A", slug="customer-a", parent_org_id=grandparent.id)
    db_session.add(parent)
    await db_session.flush()

    child = Org(name="Customer A — Site 1", slug="customer-a-site1", parent_org_id=parent.id)
    db_session.add(child)
    await db_session.flush()

    assert child.parent_org_id == parent.id
    assert parent.parent_org_id == grandparent.id
    assert grandparent.parent_org_id is None


async def test_parent_org_id_pointing_to_nonexistent_uuid_fails(db_session):
    """FK constraint must reject a parent_org_id that doesn't reference a real row."""
    bogus = Org(name="Orphan", slug="orphan", parent_org_id=uuid4())
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_multiple_children_of_same_parent(db_session):
    """A single parent can have arbitrarily many children — parallel sub-units."""
    parent = Org(name="HQ", slug="hq")
    db_session.add(parent)
    await db_session.flush()

    children = [
        Org(name=f"Site {i}", slug=f"site-{i}", parent_org_id=parent.id)
        for i in range(5)
    ]
    db_session.add_all(children)
    await db_session.flush()
    assert all(c.parent_org_id == parent.id for c in children)
