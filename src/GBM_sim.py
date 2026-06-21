import numpy as np
import pandas as pd
from pathlib import Path
import yfinance as yf
import requests
import logging
import json 


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent

class YahooExtractor:
    def __init__(self):
        self.stock_info = self._get_stock_info()
        self.tickers = self._extract_tickers()

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
        extracts isin numbers and currency of stocks in the portfolio
        '''
        df_full = self._get_positions_df()
        df = df_full[['inst_isin', 'inst_currency']]
        return df

    def _extract_tickers(self) -> list:
        """
        Converts ISIN numbers to Yahoo Finance Tickers.
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
                    # Sprawdzamy, czy Yahoo znalazło jakiekolwiek dopasowanie
                    try:
                        tickers.append(data['quotes'][0]['symbol'])
                    except (KeyError, IndexError) as e:
                        logging.error(f"Error during matching isin to ticker: {e}", exc_info=True)
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
    
    def _save_tickers(self):
        path = self.output_folder / 'tickers.json'
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.tickers, f)

    def _save_csv(self, df: pd.DataFrame):
        start_date = df['Date'].iloc[0]
        end_date = df['Date'].iloc[-1]
        df.to_csv(self.output_folder / f"hist_data_{start_date}-{end_date}.csv", index=False)

    def get_historical_data(self)->pd.DataFrame:    
        tickers = self.tickers    
        df = yf.download(tickers, period='1y')['Close']
        df = df.reset_index()
        df = self._mask_real_values(df=df)
        df = df.ffill().bfill()
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        self._save_csv(df=df)
        self._save_tickers()

        return df
        

class DataCreator:
    def __init__(self):
        self.input_path = PROJECT_DIR / 'mock_data' / 'hist_mock_data'


    def _get_data(self):
        path = self.input_path
        files = sorted(list(path.glob('*.csv')))
        if not files:
            raise FileNotFoundError(f"No csv files found in directory: {path}")
        latest_file = files[-1]
        df = pd.read_csv(latest_file)
        return df
    
    def _get_log_return(self):
        # Log returns and volatility 
        df = self._get_data()
        df = df.sort_values('Data')
        df['returns'] = np.log(df['Zamkniecie'] / df['Zamkniecie'].shift(1))
        daily_sigma = df['Zwroty'].std()
        annual_sigma_fx = daily_sigma * np.sqrt(252)
        S0 = df['Zamkniecie'].iloc[-1]


extractor = YahooExtractor()
data = extractor.get_historical_data() 
print(data)
