"""Dettagli delle porte letti dal monitor (stato amministrativo, duplex, errori, PoE) e PoE dello switch

Revision ID: bb9c9cc3889a
Revises: 9dd4314da999
Create Date: 2026-11-16 17:43:51.307250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb9c9cc3889a'
down_revision: Union[str, None] = '9dd4314da999'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('ports_polled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('devices', sa.Column('poe_budget_w', sa.Integer(), nullable=True))
    op.add_column('devices', sa.Column('poe_used_w', sa.Integer(), nullable=True))
    op.add_column('interfaces', sa.Column('admin_status', sa.String(length=10), nullable=True))
    op.add_column('interfaces', sa.Column('duplex', sa.String(length=4), nullable=True))
    op.add_column('interfaces', sa.Column('in_errors', sa.BigInteger(), nullable=True))
    op.add_column('interfaces', sa.Column('out_errors', sa.BigInteger(), nullable=True))
    op.add_column('interfaces', sa.Column('in_discards', sa.BigInteger(), nullable=True))
    op.add_column('interfaces', sa.Column('out_discards', sa.BigInteger(), nullable=True))
    op.add_column('interfaces', sa.Column('errors_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('interfaces', sa.Column('poe_status', sa.String(length=10), nullable=True))
    op.add_column('interfaces', sa.Column('poe_class', sa.Integer(), nullable=True))
    op.add_column('interfaces', sa.Column('poe_power_mw', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('interfaces', 'poe_power_mw')
    op.drop_column('interfaces', 'poe_class')
    op.drop_column('interfaces', 'poe_status')
    op.drop_column('interfaces', 'errors_at')
    op.drop_column('interfaces', 'out_discards')
    op.drop_column('interfaces', 'in_discards')
    op.drop_column('interfaces', 'out_errors')
    op.drop_column('interfaces', 'in_errors')
    op.drop_column('interfaces', 'duplex')
    op.drop_column('interfaces', 'admin_status')
    op.drop_column('devices', 'poe_used_w')
    op.drop_column('devices', 'poe_budget_w')
    op.drop_column('devices', 'ports_polled_at')
