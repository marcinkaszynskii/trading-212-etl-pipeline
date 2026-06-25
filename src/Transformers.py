import pandas as pd 
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent

class DataFormatter:
    def __init__(self):
        

        self.raw_currency_path = PROJECT_DIR / 'raw_data' / 'raw_currency_data'
        self.raw_cash_path = PROJECT_DIR / 'raw_data' / 'raw_trading_data' / 'raw_cash_data'
        self.raw_positions_path = PROJECT_DIR / 'raw_data' / 'raw_trading_data' / 'raw_positions_data'

        self.output_folder = PROJECT_DIR / 'clean_data'

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
        self.clean_currency_path = PROJECT_DIR / 'clean_data' / 'clean_currency_data'
        self.clean_cash_path = PROJECT_DIR / 'clean_data' / 'clean_trading_data' / 'clean_cash_data'
        self.clean_positions_path = PROJECT_DIR / 'clean_data' / 'clean_trading_data' / 'clean_positions_data'
        
        self.output_folder = PROJECT_DIR / 'gold_data'
        
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
        cols_to_fix = ['current_price', 'average_price_paid']
        self.positions_df.loc[mask, cols_to_fix] = self.positions_df.loc[mask, cols_to_fix] / 100
        self.positions_df.loc[mask, 'inst_currency'] = 'GBP'

    def _calculate_position_pct(self):  
        df = self.positions_df.merge(self.cash_df[['date', 'total']], on='date')
        df['position_wallet_share'] = df['wallet_current_value'] / df['total']
        self.positions_df = df.drop(columns=['total'])
        
    def _calculate_roi(self):
        self.positions_df['position_roi'] = self.positions_df['wallet_unrealized_profit_loss'] / \
        self.positions_df['wallet_total_cost']

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

    def _camel_to_snake_case(self, df:pd.DataFrame):
        col_names = df.columns.tolist()
        snake_case_names = []
        for col in df.columns:
            snake_name = ""
            for index, letter in enumerate(col):
                if letter.isupper():
                    if index > 0:
                        snake_name += "_" 
                    snake_name += letter.lower()
                else:   
                    snake_name += letter
            snake_case_names.append(snake_name)
        return snake_case_names

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
            self.cash_df.columns = self._camel_to_snake_case(self.cash_df)
            self._save_cash()
        except Exception as e: 
            logger.error(f"cash Transformation failed: {e}")
            raise
    
    def transform_positions(self):
        try:
            if self.cash_df is None:
                self.cash_df = self._get_latest_cash()
            self.positions_df = self._get_latest_positions()
            self.positions_df.columns = self._camel_to_snake_case(self.positions_df)
            self._GBX_to_GBP()
            self._calculate_roi()
            self._get_country_code()
            self._calculate_position_pct()
            self._save_positions()
            
        except Exception as e: 
            logger.error(f"positions Transformation failed: {e}")
            raise

    def transform_currency(self):
        try:
            if self.cash_df is None: 
                self.cash_df = self._get_latest_cash()
            self.currency_df = self._get_latest_currency()
            self._add_actual_date()
            self.currency_df.columns = self._camel_to_snake_case(self.currency_df)
            self._save_currency()
        except Exception as e: 
            logger.error(f"currency Transformation failed: {e}")
            raise    

    def transform_all(self):
        try:
            self.transform_cash()
            self.transform_positions()
            self.transform_currency()
            return "Transformation completed successfully."
        except Exception as e:
            logger.error(f"Transformation pipeline failed: {e}")
            raise
        


class SimulationTransformer:
    def __init__(self):
        self.gold_positions_path = PROJECT_DIR / 'gold_data' / 'gold_trading_data' / 'gold_positions_data'
        self.gold_currency_path = PROJECT_DIR / 'gold_data' / 'gold_currency_data'
        self.gold_cash_path = PROJECT_DIR / 'gold_data' / 'gold_trading_data' / 'gold_cash_data'

        self.mock_cash_path = PROJECT_DIR / 'mock_data' / 'mock_cash.json'
        self.sim_data_path = PROJECT_DIR / 'mock_data' / 'generated_data' 

        self.output_folder = PROJECT_DIR / 'gold_data' / 'gold_simulations'
        self.output_folder.mkdir(parents=True, exist_ok=True)

    def _get_latest_file(self, path):
        files = sorted(list(path.glob('*.csv')))
        if not files:
            raise FileNotFoundError(f"No csv files in: {path}")
        return files[-1]

    def _get_gold_data(self):
        pos_df = pd.read_csv(self._get_latest_file(self.gold_positions_path))
        cash_df = pd.read_csv(self._get_latest_file(self.gold_cash_path))
        curr_df = pd.read_csv(self._get_latest_file(self.gold_currency_path))
        sim_df = pd.read_csv(self._get_latest_file(self.sim_data_path))
        return pos_df, cash_df, curr_df, sim_df
    
    def _unpivot_simulations(self, sim_df):
        """
        Changes the table format from wide to long.
        """
        return sim_df.melt(id_vars=["date"], var_name="sim_ticker", value_name="sim_price")

    def _get_ticker_mapping(self):
        """
        maps t212 tickers witch yahoo tickers.
        """
        yf_path = PROJECT_DIR / 'mock_data' / 'hist_mock_data' / 'tickers_yf.json'
        t212_path = PROJECT_DIR / 'mock_data' / 'hist_mock_data' / 'tickers_212.json'
        
        with open(yf_path, 'r') as f:
            tickers_yf = json.load(f)
        with open(t212_path, 'r') as f:
            tickers_212 = json.load(f)
            
        ticker_mapping = {}
        for yf, t212 in zip(tickers_yf, tickers_212):
            ticker_mapping[f"MOCK_{yf}"] = t212     
        return ticker_mapping
    
    def _merge_and_calculate_positions(self, sim_long_df, pos_df, curr_df):
        """
        Formatting df, and calculates required metrics 
        """
        mapping_dict = self._get_ticker_mapping()
        sim_long_df['inst_ticker']= sim_long_df['sim_ticker'].map(mapping_dict)

        fx_rates = curr_df[['code', 'mid']].rename(columns={'code': 'inst_currency'})
        pos_fx_df = pos_df.merge(fx_rates, on='inst_currency', how='left')

        # Static columns that we copy from gold_positions
        cols_from_pos = [
            'inst_ticker', 'quantity', 'quantity_available_for_trading', 'quantity_in_pies', 'wallet_total_cost', 'mid',
            'inst_name', 'inst_isin', 'inst_currency', 'country_code',
            'created_at', 'average_price_paid', 'wallet_currency', 'wallet_fx_impact'
        ]

        df_merged = sim_long_df.merge(pos_fx_df[cols_from_pos], on='inst_ticker', how='left').dropna(subset=['quantity'])

        df_merged['date'] = df_merged['date']
        df_merged['current_price'] = df_merged['sim_price']
        
        # Calcultions
        df_merged['wallet_current_value'] = df_merged['current_price'] * df_merged['quantity'] * df_merged['mid']
        df_merged['wallet_unrealized_profit_loss'] = df_merged['wallet_current_value'] - df_merged['wallet_total_cost']
        df_merged['position_roi'] = df_merged['wallet_unrealized_profit_loss'] / df_merged['wallet_total_cost']

        return df_merged
    
    def _generate_currency_report(self, sim_positions_df, curr_df):
        """
        This method generates dates, and formats the df to the gold_currency format.
        The actual rates stay unchanged
        """
        future_dates = sim_positions_df['date'].unique()
        df_dates = pd.DataFrame({'date': future_dates})
        
        latest_date = curr_df['date'].max()
        latest_rates = curr_df[curr_df['date'] == latest_date].copy()
        
        latest_rates = latest_rates.drop(columns=['date', 'effective_date'], errors='ignore')
        
        sim_currency_df = df_dates.merge(latest_rates, how='cross')
        sim_currency_df['effective_date'] = sim_currency_df['date']
        
        return sim_currency_df[['date', 'code', 'currency', 'mid', 'effective_date']]

    def _generate_cash_report(self, sim_positions_df, cash_df):
        """
        Creates a dataframe in the same format as gold_cash with values calculated based on the simulation
        """
        sim_cash_df = sim_positions_df.groupby('date').agg(
            invested=('wallet_current_value', 'sum'),
            ppl=('wallet_unrealized_profit_loss', 'sum')
        ).reset_index()

        free_cash = cash_df['free'].iloc[-1]
        blocked_cash = cash_df['blocked'].iloc[-1]
        pie_cash = cash_df['pie_cash'].iloc[-1]
        
        sim_cash_df['free'] = free_cash
        sim_cash_df['blocked'] = blocked_cash
        sim_cash_df['pie_cash'] = pie_cash
        sim_cash_df['total'] = sim_cash_df['free'] + sim_cash_df['invested'] + blocked_cash + pie_cash
        sim_cash_df['result'] = sim_cash_df['ppl']
        
        sim_cash_df['free_cash_pct'] = sim_cash_df['free'] / sim_cash_df['total']
        sim_cash_df['invested_cash_pct'] = sim_cash_df['invested'] / sim_cash_df['total']
        
        return sim_cash_df[['free', 'total', 'ppl', 'result', 'invested', 'pie_cash', 'blocked', 'date', 'free_cash_pct', 'invested_cash_pct']]

    def _finalize_positions(self, sim_positions_df, sim_cash_df):
        """
        Adding total value, wallet share and setting columns in order.
        """
        
        df_final = sim_positions_df.merge(sim_cash_df[['date', 'total']], on='date', how='left')
        df_final['position_wallet_share'] = df_final['wallet_current_value'] / df_final['total']
        
        final_cols = [
            'created_at', 'quantity', 'quantity_available_for_trading', 'quantity_in_pies',
            'current_price', 'average_price_paid', 'inst_ticker', 'inst_name', 'inst_isin',
            'inst_currency', 'wallet_currency', 'wallet_total_cost', 'wallet_current_value',
            'wallet_unrealized_profit_loss', 'wallet_fx_impact', 'date', 'position_roi',
            'country_code', 'position_wallet_share'
        ]
        return df_final[final_cols]

    def run_sim_transformation_pipeline(self):
        try:
            pos_df, cash_df, curr_df, df_sim = self._get_gold_data()
            sim_long_df = self._unpivot_simulations(df_sim)
            temp_pos_df = self._merge_and_calculate_positions(sim_long_df, pos_df, curr_df)
            sim_cash_df = self._generate_cash_report(temp_pos_df, cash_df)
            sim_positions_df = self._finalize_positions(temp_pos_df, sim_cash_df)
            sim_currency_df = self._generate_currency_report(sim_positions_df, curr_df)
            
            start_date = sim_positions_df['date'].iloc[0]
            end_date = sim_positions_df['date'].iloc[-1]

            self.output_folder.mkdir(parents=True, exist_ok=True)
            
            sim_positions_df.to_csv(self.output_folder / f"gold_sim_positions_{start_date}_to_{end_date}.csv", index=False)
            sim_cash_df.to_csv(self.output_folder / f"gold_sim_cash_{start_date}_to_{end_date}.csv", index=False)
            sim_currency_df.to_csv(self.output_folder / f"gold_sim_currency_{start_date}_to_{end_date}.csv", index=False)
            
            logger.info("csv files succesfully created")
                
        except Exception as e:
            logger.error(f"Pipeline has failed: {e}")
            raise

