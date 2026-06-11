import pandas as pd 
from pathlib import Path
import json
import logging

class DataFormatter:
    def __init__(self):
        
        self.raw_currency_path = Path('/opt/airflow/raw_data/raw_currency_data')
        self.raw_cash_path = Path('/opt/airflow/raw_data/raw_trading_data/raw_cash_data')
        self.raw_positions_path = Path('/opt/airflow/raw_data/raw_trading_data/raw_positions_data')

        self.output_folder = Path('/opt/airflow/clean_data')

        self.output_folder.mkdir(exist_ok=True)      

    def _get_latest_file(self, path):       
        files = sorted(list(path.glob('*.json')))
        if not files:
            raise FileNotFoundError(f"No JSON files found in directory: {path}")
        latest_file = files[-1]
        raw_data = latest_file.read_text(encoding='utf-8')
        data_dict = json.loads(raw_data)

        # Standardize output to DataFrame regardless of input JSON structure
        if isinstance(data_dict, list):
            latest_data = pd.DataFrame(data_dict)
        else:
            latest_data = pd.DataFrame([data_dict])
        return {'latest_data':latest_data, "latest_file":latest_file}

    def _get_file_date(self, path):
        file_name = self._get_latest_file(path=path)['latest_file'].stem
        file_date = file_name[-10:]
        return file_date
    
    def _save_csv(self, data: pd.DataFrame, date_str, clean_path: Path, prefix):
        clean_path.mkdir(parents=True, exist_ok=True)
        data.to_csv(clean_path / f"{prefix}_{date_str}.csv", index=False)    

    def format_cash(self):
        df = self._get_latest_file(self.raw_cash_path)['latest_data']
        date_str = self._get_file_date(self.raw_cash_path)
        df['date'] = date_str
        clean_path = self.output_folder / Path('clean_trading_data/clean_cash_data')
        prefix = 'clean_cash_data'
        self._save_csv(data=df, date_str=date_str, clean_path=clean_path, prefix=prefix)
        return df
    
    def format_positions(self):
        """
        flattens recived nested data
        """
        df = self._get_latest_file(self.raw_positions_path)['latest_data']
        df_instrument = pd.json_normalize(df['instrument'])
        df_instrument = df_instrument.add_prefix('inst_')
        df_wallet = pd.json_normalize(df['walletImpact'])
        df_wallet.columns = [f"wallet_{col}" for col in df_wallet.columns]
        df_final = pd.concat([df.drop(['instrument', 'walletImpact'], axis=1), 
                             df_instrument, 
                             df_wallet], axis=1)
        date_str = self._get_file_date(self.raw_positions_path)
        df_final['date'] = date_str
        clean_path = self.output_folder / Path('clean_trading_data/clean_positions_data')
        prefix = 'clean_positions_data'
        self._save_csv(data=df_final, date_str=date_str, clean_path=clean_path, prefix=prefix)        
        return df_final
    
    def format_currency(self):
        """
        flattens recived nested data
        """
        df = self._get_latest_file(self.raw_currency_path)['latest_data']
        rates = df['rates'].explode()
        rates = pd.DataFrame(rates.tolist())
        date_str = df.loc[0, 'effectiveDate']
        rates['effectiveDate'] = date_str
        clean_path = self.output_folder / Path('clean_currency_data')
        prefix = 'clean_currency_data'
        self._save_csv(data=rates, date_str=date_str, clean_path=clean_path, prefix=prefix)           
        return rates    
    
class DataTransformer:
    def __init__(self):
        
        self.clean_currency_path = Path('/opt/airflow/clean_data/clean_currency_data')
        self.clean_cash_path = Path('/opt/airflow/clean_data/clean_trading_data/clean_cash_data')
        self.clean_positions_path = Path('/opt/airflow/clean_data/clean_trading_data/clean_positions_data')
        
        self.output_folder = Path("/opt/airflow/gold_data/")
        
        self.positions_df = None
        self.cash_df = None
        self.currency_df = None

    def _get_latest_data(self, path):
        files = sorted(list(path.glob('*.csv')))
        if not files:
            raise FileNotFoundError(f"No csv files found in directory: {path}")
        latest_file = files[-1]
        df = pd.read_csv(latest_file)
        return df

    def _get_latest_positions(self):
        return self._get_latest_data(self.clean_positions_path)

    def _get_latest_cash(self):
        return self._get_latest_data(self.clean_cash_path)

    def _get_latest_currency(self):
        return self._get_latest_data(self.clean_currency_path)

    def _GBX_to_GBP(self): # Needed for the consistency with the currencies pulled from NBP
        mask = self.positions_df['inst_currency'] == 'GBX'
        cols_to_fix = ['currentPrice', 'averagePricePaid']
        self.positions_df.loc[mask, cols_to_fix] = self.positions_df.loc[mask, cols_to_fix] / 100
        self.positions_df.loc[mask, 'inst_currency'] = 'GBP'

    def _calculate_position_pct(self):  
        df = self.positions_df.merge(self.cash_df[['date', 'total']], on='date')
        df['position_wallet_share'] = df['wallet_currentValue'] / df['total']
        self.positions_df = df.drop(columns=['total'])
        
    def _calculate_ROI(self):
        self.positions_df['position_ROI'] = self.positions_df['wallet_unrealizedProfitLoss'] / \
        self.positions_df['wallet_totalCost']

    def _get_country_code(self):
        self.positions_df['country_code'] = self.positions_df['inst_isin'].str[:2]
    
    def _calculate_cash_pct(self):
        self.cash_df['free_cash_pct'] = self.cash_df['free'] / self.cash_df['total']
        self.cash_df['invested_cash_pct'] = self.cash_df['invested'] / self.cash_df['total']    
    
    def _add_actual_date(self): 
        '''
        adds the date that matches dates in other dataframes so it is easy to join
        '''
        self.currency_df['date'] = self.cash_df['date'].iloc[-1]

    def _save_csv(self, data: pd.DataFrame, date_str, gold_path:Path, prefix):
        gold_path.mkdir(parents=True, exist_ok=True)       
        data.to_csv(gold_path / f"{prefix}_{date_str}.csv", index=False)
    
    def _save_cash(self):
        gold_path = self.output_folder / Path('gold_trading_data/gold_cash_data')
        self._save_csv(data=self.cash_df, 
                       date_str=self.cash_df['date'].iloc[-1],
                       gold_path=gold_path,
                       prefix='gold_cash_data')   

    def _save_positions(self):
        gold_path = self.output_folder / Path('gold_trading_data/gold_positions_data')
        self._save_csv(data=self.positions_df, 
                       date_str=self.positions_df['date'].iloc[-1],
                       gold_path=gold_path,
                       prefix='gold_positions_data')   
    
    def _save_currency(self):
        gold_path = self.output_folder / Path('gold_currency_data')
        self._save_csv(data=self.currency_df, 
                       date_str=self.currency_df['date'].iloc[-1],
                       gold_path=gold_path,
                       prefix='gold_currency_data')

    def transform_cash(self):
        try:
            self.cash_df = self._get_latest_cash()
            self._calculate_cash_pct()
            self._save_cash()
        except Exception as e: 
            logging.error(f"cash Transformation failed: {e}")
            raise
    
    def transform_positions(self):
        try:
            if self.cash_df is None:
                self.cash_df = self._get_latest_cash()
            self.positions_df = self._get_latest_positions()
            self._GBX_to_GBP()
            self._calculate_ROI()
            self._get_country_code()
            self._calculate_position_pct()
            self._save_positions()
        except Exception as e: 
            logging.error(f"positions Transformation failed: {e}")
            raise

    def transform_currency(self):
        try:
            if self.cash_df is None: 
                self.cash_df = self._get_latest_cash()
            self.currency_df = self._get_latest_currency()
            self._add_actual_date()
            self._save_currency()
        except Exception as e: 
            logging.error(f"currency Transformation failed: {e}")
            raise    

    def transform_all(self):
        try:
            self.transform_cash()
            self.transform_positions()
            self.transform_currency()
            return "Transformation completed successfully."
        except Exception as e:
            logging.error(f"Transformation pipeline failed: {e}")
            raise
        