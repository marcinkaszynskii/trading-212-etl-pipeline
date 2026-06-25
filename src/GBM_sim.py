import numpy as np
import pandas as pd
from pathlib import Path
import yfinance as yf
import requests
import logging
import json 

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent

class YahooExtractor:
    def __init__(self):
        self.stock_info = self._get_stock_info()
        self.yf_tickers = self._extract_yf_tickers()
        self.date = self._get_date()

        self.output_folder = PROJECT_DIR / 'mock_data' / 'hist_mock_data'
        self.output_folder.mkdir(parents=True, exist_ok=True)

    
    def _get_positions_df(self):
        path = PROJECT_DIR / 'gold_data' / 'gold_trading_data' / 'gold_positions_data'
        files = sorted(list(path.glob('*.csv')))
        if not files:
            raise FileNotFoundError(f"No csv files found in directory: {path}")
        latest_file = files[-1]
        df = pd.read_csv(latest_file)
        return df
 
    def _get_stock_info(self):
        '''
        extracts isin numbers, tickers and date of stocks in the portfolio
        '''
        df_full = self._get_positions_df()
        df = df_full[['date', 'inst_isin', 'inst_ticker']]
        return df
    
    def _clean_mock_tickers(self):
        tickers = self.stock_info()['inst_ticker']
        tickers = tickers.str()

    def _get_date(self):
        stock_date = self.stock_info['date'].iloc[0]
        stock_date = pd.to_datetime(stock_date)
        return stock_date
    
    def _extract_yf_tickers(self) -> list:
        """
        Converts ISIN numbers to Yahoo Finance Tickers. This is done by disguising 
        as a browser, and searching by ISIN on the website.  
        """
        isins = self.stock_info['inst_isin']
        tickers = []
        headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        
        with requests.Session() as session:
            session.headers.update(headers)

            for isin in isins:
                url = f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}"
                
                try:
                    response = session.get(url)
                    response.raise_for_status() 
                    data = response.json()                
                    try:
                        tickers.append(data['quotes'][0]['symbol'])
                    except (KeyError, IndexError) as e:
                        logger.error(f"Error during matching isin to ticker: {e}", exc_info=True)
                        tickers.append(None)
                except requests.exceptions.RequestException as e:
                    print(f"Connection error for isin '{isin}': {e}")
                    tickers.append(None)
        return tickers
    
    def _mask_real_values(self, df):
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            multipliers = np.random.uniform(1 - 0.005, 1 + 0.005, size=len(df))
            df[col] = df[col] * multipliers
        
        return df
    
    def _save_yf_tickers(self):
        path = self.output_folder / 'tickers_yf.json'
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.yf_tickers, f)

    def _save_212_tickers(self):
        path = self.output_folder / 'tickers_212.json'
        tickers_212 = self.stock_info['inst_ticker'].tolist()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tickers_212, f)

    def _save_csv(self, df: pd.DataFrame):
        start_date = df['Date'].iloc[0]
        end_date = df['Date'].iloc[-1]
        df.to_csv(self.output_folder / f"hist_data_{start_date}-{end_date}.csv", index=False)

    def get_historical_data(self)->pd.DataFrame:    
        end_date = self._get_date()
        start_date = end_date - pd.DateOffset(years=3) 
        end_date = end_date.strftime('%Y-%m-%d')
        start_date = start_date.strftime('%Y-%m-%d')

        tickers = self.yf_tickers    
        df = yf.download(tickers, start=start_date, end=end_date)['Close']
        df = df.reset_index()
        df = self._mask_real_values(df=df)
        df = df.ffill().bfill()
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        self._save_csv(df=df)
        self._save_yf_tickers()
        self._save_212_tickers()
        

class DataGenerator:
    def __init__(self):
        self.input_path = PROJECT_DIR / 'mock_data' / 'hist_mock_data'
        self.output_folder = PROJECT_DIR / 'mock_data' / 'generated_data'
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.input_212_ticker_path = PROJECT_DIR / 'mock_data' / 'mock_positions.json'

        self.tickers = self._get_tickers()
        self.full_data = self._get_data()
        self.data_dict = self._split_data()
        

    def _get_tickers(self):
        path = self.input_path / 'tickers_yf.json'
        with open(path, "r", encoding="utf-8") as file:
            tickers = json.load(file)
        return tickers 

    def _get_data(self):
        path = self.input_path
        files = sorted(list(path.glob('*.csv')))
        if not files:
            raise FileNotFoundError(f"No csv files found in directory: {path}")
        latest_file = files[-1]
        df = pd.read_csv(latest_file)
        return df
    
    def _split_data(self):
        data_dict = {}
        for ticker in self.tickers:
            data_dict[ticker] = self.full_data[['Date', ticker]]
        return data_dict

    def _get_gbm_params(self):
        gbm_params = {}
        for ticker in self.data_dict.keys():
            df = self.data_dict[ticker]
            df = df.sort_values('Date')
            
            # Log returns 
            df['returns'] = np.log(df[ticker] / df[ticker].shift(1))
            
            # volatility (daily and annual)
            daily_sigma = df['returns'].std()
            annual_sigma = daily_sigma * np.sqrt(260)

            # Starting point
            S0 = df[ticker].iloc[-1]

            # annual drift
            daily_drift = df["returns"].mean()
            annual_drift = daily_drift * 260 + (annual_sigma**2) / 2

            gbm_params[ticker] = {
                "S0": S0,
                "sigma": annual_sigma,
                "drift": annual_drift,
            }
        return gbm_params
    
    def _gbm_engine(self, param_dict:dict):
        horizont_years = 1 
        n_steps = horizont_years * 260

        start_date = self.full_data['Date'].iloc[-1]
        dates = pd.bdate_range(start=start_date, periods=n_steps + 1)
        dt = 1/260

        simulated_data = {}

        for ticker, params in param_dict.items():
            S0 = params['S0']
            drift = params["drift"]
            sigma = params["sigma"]

            t = np.linspace(dt, n_steps * dt, n_steps)

            rnd = np.random.standard_normal(n_steps)
            # Cumulative noise over time (Wiener Process)
            W = np.cumsum(rnd) * np.sqrt(dt)

            # GBM equation 
            prices = S0 * np.exp((drift - 0.5 * sigma**2) * t + sigma * W)

            price_path = np.insert(prices, 0, S0)

            df_sim = pd.DataFrame({
                "Date": dates.strftime('%Y-%m-%d'),
                "Price": price_path
            })

            simulated_data[ticker] = df_sim
        return simulated_data

    def _merge_df(self, data: dict):
        merged_df = pd.DataFrame()

        for ticker, current_df in data.items():
            temp_df = current_df.rename(columns={"Price": f"MOCK_{ticker}"})
            if merged_df.empty:     
                    merged_df = temp_df
            else:
                merged_df = pd.merge(merged_df, temp_df, on="Date")
            
        return merged_df

    def _save_csv(self, df):
        start_date = df['date'].iloc[0]
        end_date = df['date'].iloc[-1]
        df.to_csv(self.output_folder / f"sim_data_{start_date}_to_{end_date}.csv", index=False)

    def generate_data(self):
        gbm_params = self._get_gbm_params()
        simulated_data_dict = self._gbm_engine(param_dict=gbm_params)
        simulated_data = self._merge_df(simulated_data_dict)
        simulated_data = simulated_data.rename(columns={'Date':'date'})
        self._save_csv(simulated_data)
