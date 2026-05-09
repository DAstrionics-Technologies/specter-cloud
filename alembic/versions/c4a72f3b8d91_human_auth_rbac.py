"""human auth + RBAC

Adds:
  - parent_org_id column on orgs (self-FK, ondelete RESTRICT)
  - users table (with email lockout fields, email_verified_at, last_login_at)
  - roles table + seeds 6 roles (3 user-facing in cloud v1 commercial,
    3 reserved for GCS personas + Specter-only platform role)
  - user_roles join table (composite PK, soft-delete via revoked_at)
  - sessions table (token_hash storage, transport: cookie | bearer)
  - audit_log table (append-only, partial index on deny decisions)

Revision ID: c4a72f3b8d91
Revises: ad02ee5908dd
Create Date: 2026-05-08 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4a72f3b8d91"
down_revision: Union[str, None] = "ad02ee5908dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----- orgs: add parent_org_id -----
    op.add_column(
        "orgs",
        sa.Column("parent_org_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orgs_parent_org_id",
        "orgs",
        "orgs",
        ["parent_org_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_orgs_parent_org_id"),
        "orgs",
        ["parent_org_id"],
    )

    # ----- users -----
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index(op.f("ix_users_org_id"), "users", ["org_id"])

    # ----- roles -----
    op.create_table(
        "roles",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "is_platform_role",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    # Seed the 6 roles. Stable IDs across all environments.
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", sa.SmallInteger),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("is_platform_role", sa.Boolean),
        ),
        [
            {
                "id": 1,
                "name": "viewer",
                "description": "Read-only access to drones, telemetry, video, missions.",
                "is_platform_role": False,
            },
            {
                "id": 2,
                "name": "operator",
                "description": "Fly drones, design and execute missions.",
                "is_platform_role": False,
            },
            {
                "id": 3,
                "name": "planner",
                "description": "Design missions; GCS-side persona, no cloud permissions in v1.",
                "is_platform_role": False,
            },
            {
                "id": 4,
                "name": "technician",
                "description": "Hardware setup, calibration, firmware, log analysis; GCS-side persona, no cloud permissions in v1.",
                "is_platform_role": False,
            },
            {
                "id": 5,
                "name": "developer",
                "description": "Specter-internal: advanced drone params, platform tooling, dev diagnostics. Granted only at Specter root org.",
                "is_platform_role": True,
            },
            {
                "id": 6,
                "name": "admin",
                "description": "User management, org settings, audit access. Scope determined by org tier of grant.",
                "is_platform_role": False,
            },
        ],
    )

    # ----- user_roles -----
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("user_id", "org_id", "role_id"),
    )
    # Hot-path partial indexes — only active grants. Postgres will skip the
    # WHERE-clause cost on lookups against these indexes.
    op.create_index(
        "ix_user_roles_active",
        "user_roles",
        ["user_id", "org_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_user_roles_org_active",
        "user_roles",
        ["org_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # ----- sessions -----
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index(
        "ix_sessions_user_active",
        "sessions",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        op.f("ix_sessions_token_hash"),
        "sessions",
        ["token_hash"],
    )

    # ----- audit_log -----
    op.create_table(
        "audit_log",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("permission", sa.String(length=60), nullable=True),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("target_org_id", sa.Uuid(), nullable=True),
        sa.Column("matched_role_id", sa.SmallInteger(), nullable=True),
        sa.Column("matched_org_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_org_id"], ["orgs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["matched_role_id"], ["roles.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["matched_org_id"], ["orgs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_user_time",
        "audit_log",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_resource",
        "audit_log",
        ["resource_type", "resource_id", "created_at"],
    )
    # Partial index for deny audits — cheap to grow, fast to query for security review.
    op.create_index(
        "ix_audit_deny_time",
        "audit_log",
        ["created_at"],
        postgresql_where=sa.text("decision = 'deny'"),
    )


def downgrade() -> None:
    op.drop_index("ix_audit_deny_time", table_name="audit_log")
    op.drop_index("ix_audit_resource", table_name="audit_log")
    op.drop_index("ix_audit_user_time", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index(op.f("ix_sessions_token_hash"), table_name="sessions")
    op.drop_index("ix_sessions_user_active", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_user_roles_org_active", table_name="user_roles")
    op.drop_index("ix_user_roles_active", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_table("roles")

    op.drop_index(op.f("ix_users_org_id"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_orgs_parent_org_id"), table_name="orgs")
    op.drop_constraint("fk_orgs_parent_org_id", "orgs", type_="foreignkey")
    op.drop_column("orgs", "parent_org_id")
