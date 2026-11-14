"""Rilettura di un solo device ("Rileggi ora"): indirizzo dell'esecuzione al posto di quelli del job

Revision ID: 01ddcf0afedb
Revises: d495009c13c1
Create Date: 2026-11-14 17:55:33.303261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01ddcf0afedb'
down_revision: Union[str, None] = 'd495009c13c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('discovery_runs', sa.Column('host', sa.String(length=45), nullable=True))


def downgrade() -> None:
    op.drop_column('discovery_runs', 'host')
