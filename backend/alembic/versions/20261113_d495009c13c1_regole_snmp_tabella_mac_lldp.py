"""Regole SNMP: porte della tabella MAC, porta locale LLDP e regole incluse in NetMap

Revision ID: d495009c13c1
Revises: 8e36e57d5bcd
Create Date: 2026-11-13 23:06:43.392685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd495009c13c1'
down_revision: Union[str, None] = '8e36e57d5bcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('snmp_rules', sa.Column('fdb_port', sa.String(length=10), nullable=True))
    op.add_column('snmp_rules', sa.Column('lldp_port_oid', sa.String(length=200), nullable=True))
    op.add_column('snmp_rules', sa.Column('builtin', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('snmp_rules', 'builtin')
    op.drop_column('snmp_rules', 'lldp_port_oid')
    op.drop_column('snmp_rules', 'fdb_port')
