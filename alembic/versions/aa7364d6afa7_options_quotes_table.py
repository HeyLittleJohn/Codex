"""options quotes table

Revision ID: aa7364d6afa7
Revises: 20b9727bdd63
Create Date: 2024-06-12 12:55:39.150819

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aa7364d6afa7'
down_revision = '20b9727bdd63'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('options_quotes',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('options_ticker_id', sa.BigInteger(), nullable=False),
    sa.Column('as_of_date', sa.DateTime(), nullable=False),
    sa.Column('ask_exchange', sa.Integer(), nullable=True),
    sa.Column('ask_price', sa.DECIMAL(precision=19, scale=4), nullable=False),
    sa.Column('ask_size', sa.Integer(), nullable=False),
    sa.Column('bid_exchange', sa.Integer(), nullable=True),
    sa.Column('bid_price', sa.DECIMAL(precision=19, scale=4), nullable=False),
    sa.Column('bid_size', sa.Integer(), nullable=False),
    sa.Column('sequence_number', sa.BigInteger(), nullable=True),
    sa.Column('sip_timestamp', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('is_overwritten', sa.Boolean(), server_default=sa.text('false'), nullable=True),
    sa.ForeignKeyConstraint(['options_ticker_id'], ['options_tickers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', name='uq_options_quotes_id'),
    )
    op.create_unique_constraint(None, 'options_snapshots', ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'options_snapshots', type_='unique')
    op.drop_table('options_quotes')
    # ### end Alembic commands ###
