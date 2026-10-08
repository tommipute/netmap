"""device nella posizione del loro rack

Revision ID: 6de2c9aae91c
Revises: 8b3b3077ecda
Create Date: 2026-10-08 15:29:11.312445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6de2c9aae91c'
down_revision: Union[str, None] = '8b3b3077ecda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Da ora un device nel rack prende la posizione del rack (rules.device_hook): allineo quelli già nei rack
    op.execute("""
        UPDATE devices SET location_id = racks.location_id
        FROM racks
        WHERE devices.rack_id = racks.id AND racks.location_id IS NOT NULL
          AND racks.site_id = devices.site_id AND devices.location_id IS DISTINCT FROM racks.location_id
    """)


def downgrade() -> None:
    pass  # le posizioni precedenti non sono salvate
