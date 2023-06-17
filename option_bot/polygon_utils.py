import asyncio
from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import Enum

import numpy as np
from aiohttp import ClientSession
from aiohttp.client_exceptions import (
    ClientConnectionError,
    ClientConnectorError,
    ClientResponseError,
)
from dateutil.relativedelta import relativedelta

from option_bot.exceptions import ProjAPIError, ProjAPIOverload, ProjIndexError
from option_bot.proj_constants import log, POLYGON_API_KEY, POLYGON_BASE_URL
from option_bot.utils import first_weekday_of_month, timestamp_to_datetime


class Timespans(Enum):
    minute = "minute"
    hour = "hour"
    day = "day"
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"


class PolygonPaginator(ABC):
    """API paginator interface for calls to the Polygon API. \
        It tracks queries made to the polygon API and calcs potential need for sleep

        self.query_all() is the universal function to query the api until all results have been returned.

        self.fetch() will ultimately result in the population of self.clean_results (a list of dicts with polygon data)
        self.clean_results will be converted into a generator that can be batch input into the db"""

    paginator_type = "Generic"

    MAX_QUERY_PER_SECOND = 99
    # MAX_QUERY_PER_MINUTE = 4  # free api limits to 5 / min which is 4 when indexed at 0

    def __init__(self):
        self.clean_results = []
        self.clean_data_generator = iter(())

    def _api_sleep_time(self) -> int:
        """Returns the time to sleep based if the endpoint returns a 429 error"""
        return 60

    def _clean_url(self, url: str) -> str:
        """Clean the url to remove the base url"""
        return url.replace(POLYGON_BASE_URL, "")

    async def _execute_request(self, session: ClientSession, url: str, payload: dict = {}) -> tuple[int, dict]:
        """Execute the request and return the response status code and json response
        Args:
            session: aiohttp ClientSession
            url: url to query
            payload: dict of query params
        Returns:
            (status_code, json_response)
                status_code: int of the response status code
                json_response: dict of the json response
        """
        payload["apiKey"] = POLYGON_API_KEY
        async with session.request(method="GET", url=url, params=payload) as response:
            status_code = response.status
            if status_code == 429:
                raise ProjAPIOverload(f"API Overload, 429 error code: {url} {payload}")
            elif status_code >= 400:
                raise ProjAPIError(f"API Error, status code {status_code}: {url} {payload}")
            json_response = await response.json() if status_code == 200 else {}
            return (status_code, json_response)

    async def _query_all(self, session: ClientSession, url: str, payload: dict = {}) -> list[dict]:
        """Query the API until all results have been returned
        Args:
            session: aiohttp ClientSession
            url: url to query
            payload: dict of query params

        Returns:
            list of dicts of the json response
        """
        results = []
        status = 0
        retry = False

        while True:
            try:
                status, response = await self._execute_request(session, url, payload)

            except ProjAPIOverload as e:
                log.exception(e)
                status = 1

            except ProjAPIError as e:
                log.exception(e)
                status = 2

            except (ClientConnectionError, ClientConnectorError, ClientResponseError) as e:
                log.exception(e, extra={"context": "Connection Lost! Going to sleep for 45 seconds..."})
                status = 3

            except Exception as e:
                log.exception(e, extra={"context": "Unexpected Error"})
                status = 4

            finally:
                if status == 200:
                    results.append(response)
                    if response.get("next_url"):
                        url = self._clean_url(response["next_url"])
                        payload = {}
                        status = 0
                        retry = False
                    else:
                        break

                elif status == 1 and retry is False:
                    await asyncio.sleep(self._api_sleep_time())
                    retry = True
                    status = 0

                elif status == 2 and retry is False:
                    retry = True
                    status = 0

                elif status == 3 and retry is False:
                    await asyncio.sleep(45)
                    retry = True
                    status = 0

                else:
                    break

        return results

    async def query_data(self, url: str, payload: dict, ticker_id: str, session: ClientSession = None):
        """query_data() is an api to call the _query_all() function.

        Overwrite this to customize the way to insert the ticker_id into the query results
        """
        return await self._query_all(session, url, payload)

    # deprecated
    def make_clean_generator(self, clean_results: list[dict]):
        try:
            record_size = len(clean_results[0])
            batch_size = round(62000 / record_size)  # postgres input limit is ~65000
            for i in range(0, len(clean_results), batch_size):
                yield clean_results[i : i + batch_size]

        except IndexError:
            if hasattr(self, "ticker"):
                t = self.ticker
            elif hasattr(self, "o_ticker"):
                t = self.o_ticker
            raise ProjIndexError(f"No results for ticker: {t}, using object: {self.paginator_type} ")

    @abstractmethod
    def clean_data(self):
        """Requiring a clean_data() function to be overwritten by every inheriting class"""

    @abstractmethod
    def generate_request_args(self):
        """Requiring a generate_request_args() function to be overwritten by every inheriting class

        Returns:
            url_args: list(tuple) of the (url, payload, and ticker_id) for each request"""

    # deprecated
    async def fetch(self, session):
        await self.query_data()
        self.clean_data()
        self.clean_data_generator = self.make_clean_generator()


class StockMetaData(PolygonPaginator):
    """Object to query the Polygon API and retrieve information about listed stocks. \
        It can be used to query for a single individual ticker or to pull the entire corpus"""

    paginator_type = "StockMetaData"

    def __init__(self, tickers: list[str], all_: bool):
        self.tickers = tickers
        self.all_ = all_
        self.payload = {"active": "true", "market": "stocks", "limit": 1000}
        super().__init__()

    def generate_request_args(self):
        """Generate the urls to query the Polygon API.

        Returns:
        urls: list(dict), each dict contains the url and the payload for the request"""
        url_base = "/v3/reference/tickers"
        if not self.all_:
            urls = [(url_base, dict(self.payload, **{"ticker": ticker}), ticker) for ticker in self.tickers]
        else:
            urls = [(url_base, self.payload, "")]
        return urls

    def clean_data(self, results: list[dict]):
        clean_results = []
        selected_keys = [
            "ticker",
            "name",
            "type",
            "active",
            "market",
            "locale",
            "primary_exchange",
            "currency_name",
            "cik",
        ]
        for result_list in results:
            for ticker in result_list["results"]:
                t = {x: ticker.get(x) for x in selected_keys}
                clean_results.append(t)
        return clean_results


class HistoricalStockPrices(PolygonPaginator):
    """Object to query Polygon API and retrieve historical prices for the underlying stock"""

    paginator_type = "StockPrices"

    def __init__(
        self,
        ticker: str,
        ticker_id: int,
        start_date: datetime,
        end_date: datetime,
        multiplier: int = 1,
        timespan: Timespans = Timespans.day,
        adjusted: bool = True,
    ):
        self.ticker = ticker
        self.ticker_id = ticker_id
        self.multiplier = multiplier
        self.timespan = timespan.value
        self.start_date = start_date.date()
        self.end_date = end_date.date()
        self.adjusted = "true" if adjusted else "false"
        super().__init__()

    async def query_data(self):
        url = f"/v2/aggs/ticker/{self.ticker}/range/{self.multiplier}/{self.timespan}/{self.start_date}/{self.end_date}"
        payload = {"adjusted": self.adjusted, "sort": "desc", "limit": 50000}
        await self.query_all(url, payload)

    def clean_data(self):
        key_mapping = {
            "v": "volume",
            "vw": "volume_weight_price",
            "c": "close_price",
            "o": "open_price",
            "h": "high_price",
            "l": "low_price",
            "t": "as_of_date",
            "n": "number_of_transactions",
            "otc": "otc",
        }
        for page in self.results:
            for record in page.get("results"):
                t = {key_mapping[key]: record.get(key) for key in key_mapping}
                t["as_of_date"] = timestamp_to_datetime(t["as_of_date"], msec_units=True)
                t["ticker_id"] = self.ticker_id
                self.clean_results.append(t)


class OptionsContracts(PolygonPaginator):
    """Object to query options contract tickers for a given underlying ticker based on given dates.
    It will pull all options contracts that exist for each underlying ticker as of the first business day of each month.
    Number of months are determined by `month_hist`"""

    paginator_type = "OptionsContracts"

    def __init__(
        self,
        ticker: str,
        ticker_id: int,
        months_hist: int = 24,
        all_: bool = False,
        ticker_id_lookup: dict | None = None,
    ):
        super().__init__()
        self.ticker = ticker
        self.ticker_id = ticker_id
        self.months_hist = months_hist
        self.base_dates = self._determine_base_dates()
        self.all_ = all_
        self.ticker_id_lookup = ticker_id_lookup

    def _determine_base_dates(self) -> list[datetime]:
        year_month_array = []
        counter = 0
        year = datetime.now().year
        month = datetime.now().month
        while counter <= self.months_hist:
            year_month_array.append(
                str(year) + "-" + str(month) if len(str(month)) > 1 else str(year) + "-0" + str(month)
            )
            if month == 1:
                month = 12
                year -= 1
            else:
                month -= 1
            counter += 1
        return [str(x) for x in first_weekday_of_month(np.array(year_month_array)).tolist()]

    async def query_data(self, session: ClientSession):
        url = "/v3/reference/options/contracts"
        payload = {"limit": 1000}
        if not self.all_:
            payload["underlying_ticker"] = self.ticker
        args_list = [[session, url, dict(payload, **{"as_of": date})] for date in self.base_dates]
        for args in args_list:
            await self.query_all(*args)

    def clean_data(self):
        key_mapping = {
            "ticker": "options_ticker",
            "expiration_date": "expiration_date",
            "strike_price": "strike_price",
            "contract_type": "contract_type",
            "shares_per_contract": "shares_per_contract",
            "primary_exchange": "primary_exchange",
            "exercise_style": "exercise_style",
            "cfi": "cfi",
        }
        for page in self.results:
            for record in page.get("results"):
                t = {key_mapping[key]: record.get(key) for key in key_mapping}
                t["underlying_ticker_id"] = (
                    self.ticker_id_lookup[record.get("underlying_ticker")] if self.all_ else self.ticker_id
                )
                self.clean_results.append(t)
        self.clean_results = list({v["options_ticker"]: v for v in self.clean_results}.values())
        # NOTE: the list(comprehension) above ascertains that all options_tickers are unique


class HistoricalOptionsPrices(PolygonPaginator):
    """Object to query Polygon API and retrieve historical prices for the options chain for a given ticker"""

    paginator_type = "OptionsPrices"

    def __init__(
        self,
        o_ticker: str,
        o_ticker_id: int,
        expiration_date: datetime,
        month_hist: int = 24,
        multiplier: int = 1,
        timespan: Timespans = Timespans.day,
        adjusted: bool = True,
    ):
        super().__init__()
        self.o_ticker = o_ticker
        self.o_ticker_id = o_ticker_id
        self.expiration_date = expiration_date  # datetime.date
        self.timespan = timespan.value
        self.multiplier = multiplier
        self.adjusted = "true" if adjusted else "false"
        self.month_hist = month_hist

    def _determine_start_end_dates(self, exp_date: date):
        end_date = datetime.now().date() if exp_date > datetime.now().date() else exp_date
        start_date = end_date - relativedelta(months=self.month_hist)
        return start_date, end_date

    async def query_data(self, session: ClientSession):
        """api call to the aggs endpoint

        Parameters:
            start_date (datetime): beginning of date range for historical query (date inclusive)
            end_date (datetime): ending of date range for historical query (date inclusive)
            timespan (str) : the default value is set to "day". \
                Options are ["minute", "hour", "day", "week", "month", "quarter", "year"]
            multiplier (int) : multiples of the timespan that should be included in the call. Defaults to 1

        """
        payload = {"adjusted": self.adjusted, "sort": "desc", "limit": 50000}
        url = (
            f"/v2/aggs/ticker/{self.o_ticker}/range/{self.multiplier}/{self.timespan}/"
            + f"{self._determine_start_end_dates(self.expiration_date)[0]}/"
            + f"{self._determine_start_end_dates(self.expiration_date)[1]}"
        )
        await self.query_all(session, url, payload)

    def clean_data(self):
        results_hash = {}
        key_mapping = {
            "v": "volume",
            "vw": "volume_weight_price",
            "c": "close_price",
            "o": "open_price",
            "h": "high_price",
            "l": "low_price",
            "t": "as_of_date",
            "n": "number_of_transactions",
        }
        for page in self.results:
            if page.get("results"):
                for record in page.get("results"):
                    t = {key_mapping[key]: record.get(key) for key in key_mapping}
                    t["as_of_date"] = timestamp_to_datetime(t["as_of_date"], msec_units=True)
                    if not results_hash.get(page["ticker"]):
                        results_hash[page["ticker"]] = []
                    results_hash[page["ticker"]].append(t)

        self._clean_record_hash(results_hash)

    def _clean_record_hash(self, results_hash: dict):
        for ticker in results_hash:
            self.clean_results.extend(
                [dict(x, **{"options_ticker_id": self.o_ticker_id}) for x in results_hash[ticker]]
            )
