"""Location SNMP dei device: il sysLocation letto dalla scansione, come testo (non diventa la Posizione)

Revision ID: 9dd4314da999
Revises: 01ddcf0afedb
Create Date: 2026-11-15 21:21:15.717918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9dd4314da999'
down_revision: Union[str, None] = '01ddcf0afedb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('sys_location', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('devices', 'sys_location')
