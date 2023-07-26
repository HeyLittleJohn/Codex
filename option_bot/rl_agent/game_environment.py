import asyncio
from datetime import datetime

from py_vollib_vectorized.implied_volatility import vectorized_implied_volatility
from py_vollib_vectorized.api import price_dataframe

from rl_agent.queries import (
    extract_ticker_price,
    extract_options_contracts,
    extract_options_prices,
    extract_game_market_data,
)
from rl_agent.constants import DAYS_TIL_EXP, ANNUAL_TRADING_DAYS, RISK_FREE
from option_bot.utils import trading_days_in_range


class GameEnvironmnet(object):
    def __init__(self, underlying_ticker: str, start_date: str, days_to_exp: int = DAYS_TIL_EXP):
        self.ticker = underlying_ticker
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d") if type(start_date) == str else start_date
        self.days_to_exp = days_to_exp
        self.end = False

    # NOTE: should this only pull for the current game and be re-called at "reset"?
    async def pull_game_price_data(self):
        # return await asyncio.gather(
        #     extract_ticker_price(self.ticker),
        #     extract_options_contracts(self.ticker, self.start_date),
        #     extract_options_prices(self.ticker, self.start_date),
        # )
        return await extract_game_market_data(self.ticker, self.start_date)

    # NOTE: may want to pull data from before the start date to calc hist volatility, etc

    async def prepare_state_data(self):
        # s_price, o_contracts, o_prices = await self.pull_game_price_data()
        df = await self.pull_game_price_data()
        df["flag"] = df["contract_type"].apply(lambda x: "c" if x.value == "call" else "p")
        # calc the time to expiration
        df["T"] = df.apply(
            lambda x: trading_days_in_range(x["as_of_date"], x["expiration_date"], "o_cal") / ANNUAL_TRADING_DAYS,
            axis=1,
        )  # NOTE: THIS IS SLOW! Need to optimize with cuDF or np.vectorize
        # reference: https://shubhanshugupta.com/speed-up-apply-function-pandas-dataframe/#3-rapids-cudf-
        # add the risk free rate
        df = df.merge(RISK_FREE, on="as_of_date")
        # calc the div yield
        # NOTE: div yield is not currently in the db

        price_dataframe(
            df,
            flag_col="flag",
            underlying_price_col="stock_close_price",
            strike_col="strike_price",
            annualized_tte_col="T",
            riskfree_rate_col="risk_free_rate",
            price_col="opt_close_price",
            model="black_scholes",  # _merton when you add dividend yield
            inplace=True,
        )

        return df

    def _impute_missing_data(self):
        # use this https://github.com/rsheftel/pandas_market_calendars to find missing days
        pass

    def reset(self):
        pass

    def step():
        pass


async def main():
    game = GameEnvironmnet("SPY", "2022-01-01")
    s_price, o_contracts, o_prices = await game.pull_game_price_data()
    print(s_price)


# NOTE: this could be used for the logic of pulling the prices to be considered for each step
"""    Attributes:
        options_tickers: List[str]
            the options contract tickers

        exp_date: [datetime, datetime]
            the range of option expiration dates to be queried

        strike_price: decimal
            the strike price range want to include in our queries

    Note:
        exp_date and strike_price are inclusive ranges"""

"""
    Attributes:
        ticker: str
            the underlying stock ticker
        base_date: [datetime]
            the date that is the basis for current observations. \
            In other words: the date at which you are looking at the chain of options data
        current_price: decimal
            The current price of the underlying ticker
    """

if __name__ == "__main__":
    asyncio.run(main())
