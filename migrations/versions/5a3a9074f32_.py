"""empty message

Revision ID: 5a3a9074f32
Revises: None
Create Date: 2015-07-10 16:21:56.791911

"""

# revision identifiers, used by Alembic.
revision = '5a3a9074f32'
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('db_game',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('a_secret', sa.Integer(), nullable=True),
    sa.Column('b_secret', sa.Integer(), nullable=True),
    sa.Column('c_secret', sa.Integer(), nullable=True),
    sa.Column('d_secret', sa.Integer(), nullable=True),
    sa.Column('state_log', sa.String(length=2048), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('db_game')
    ### end Alembic commands ###
