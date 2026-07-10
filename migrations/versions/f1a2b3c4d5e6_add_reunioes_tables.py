"""add reunioes and reuniao_participantes tables

Revision ID: f1a2b3c4d5e6
Revises: 6bad082406a6
Create Date: 2026-07-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '6bad082406a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reunioes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=300), nullable=False),
        sa.Column('criada_por', sa.Integer(), nullable=False),
        sa.Column('criada_em', sa.DateTime(), nullable=False),
        sa.Column('arquivo_audio', sa.String(length=500), nullable=True),
        sa.Column('transcricao', sa.Text(), nullable=True),
        sa.Column('ata', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('aberta', 'gravando', 'processando', 'concluida', 'erro',
                    name='reuniao_status'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['criada_por'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'reuniao_participantes',
        sa.Column('reuniao_id', sa.Integer(), nullable=False),
        sa.Column('medico_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['reuniao_id'], ['reunioes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['medico_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('reuniao_id', 'medico_id'),
    )


def downgrade():
    op.drop_table('reuniao_participantes')
    op.drop_table('reunioes')
    # remove o tipo ENUM criado (PostgreSQL não remove sozinho ao dropar a tabela)
    sa.Enum(name='reuniao_status').drop(op.get_bind(), checkfirst=True)
