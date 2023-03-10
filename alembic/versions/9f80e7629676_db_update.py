"""DB Update

Revision ID: 9f80e7629676
Revises: 74112727120a
Create Date: 2023-03-10 17:16:04.668351

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f80e7629676'
down_revision = '74112727120a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('uq_options_price', 'option_prices', type_='unique')
    op.create_unique_constraint('uq_options_price', 'option_prices', ['options_ticker_id', 'as_of_date'])
    op.create_unique_constraint(None, 'option_prices', ['id'])
    op.drop_column('option_prices', 'otc')
    op.drop_column('option_prices', 'price_date')
    op.create_unique_constraint(None, 'options_tickers', ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'options_tickers', type_='unique')
    op.add_column('option_prices', sa.Column('price_date', sa.DATE(), autoincrement=False, nullable=False))
    op.add_column('option_prices', sa.Column('otc', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.drop_constraint(None, 'option_prices', type_='unique')
    op.drop_constraint('uq_options_price', 'option_prices', type_='unique')
    op.create_unique_constraint('uq_options_price', 'option_prices', ['options_ticker_id', 'price_date', 'as_of_date'])
    # ### end Alembic commands ###