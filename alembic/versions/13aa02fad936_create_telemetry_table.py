"""create telemetry table

Revision ID: 13aa02fad936
Revises:
Create Date: 2026-04-03 10:48:28.531873
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "13aa02fad936"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telemetry",
        sa.Column(
            "time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("drone_id", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("heading", sa.Integer(), nullable=False),
        sa.Column("battery", sa.Float(), nullable=False),
        sa.Column("voltage", sa.Float(), nullable=False),
        sa.Column("armed", sa.Boolean(), nullable=False),
        sa.Column("flight_mode", sa.String(length=32), nullable=False),
        sa.Column("gps_fix_type", sa.Integer(), nullable=False),
        sa.Column("satellites", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("time", "drone_id"),
    )
    # Convert to TimescaleDB hypertable for time-series optimization
    op.execute("SELECT create_hypertable('telemetry', 'time')")


def downgrade() -> None:
    op.drop_table("telemetry")
