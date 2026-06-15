"""set location scale_type to 24h

Revision ID: b8ba4283ad02
Revises: 385908409214
Create Date: 2026-06-15 21:30:30.515701

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8ba4283ad02'
down_revision = '385908409214'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE locations SET scale_type = '24h'")


def downgrade():
    pass
