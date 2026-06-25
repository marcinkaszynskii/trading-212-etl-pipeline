from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import os    
from dotenv import load_dotenv
from urllib.parse import quote_plus
import time
from pathlib import Path
import logging


load_dotenv()
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent

class SQLLoader:
    def __init__(self):
        """
        expects .env variables: PG_USERNAME, PG_PASSWORD, PG_PORT, PG_HOST, PG_DB
        """
        self.pg_username = os.getenv('PG_USERNAME')
        self.pg_password = os.getenv('PG_PASSWORD')
        self.pg_port = os.getenv('PG_PORT')
        self.pg_host = os.getenv('PG_HOST')
        self.pg_db = os.getenv('PG_DB')     
        
        self.currency_path = PROJECT_DIR / 'gold_data' / 'gold_currency_data'
        self.cash_path = PROJECT_DIR / 'gold_data' / 'gold_trading_data' / 'gold_cash_data'
        self.positions_path = PROJECT_DIR / 'gold_data' / 'gold_trading_data' / 'gold_positions_data'

        self.simulation_path = PROJECT_DIR / 'gold_data' / 'gold_simulations'

        self.sql_engine = self._create_sql_engine() 

    def _create_sql_engine(self):
        return create_engine(f"postgresql://{self.pg_username}:\
{quote_plus(self.pg_password)}@{self.pg_host}:{self.pg_port}/{self.pg_db}")
    
    def _create_date_str(self):
        return time.strftime('%Y-%m-%d', time.localtime())

    def _execute_query(self, query):
        try:
            with self.sql_engine.begin() as conn:
                conn.execute(query)
        except SQLAlchemyError as e:
            logger.error(f"Database error during table creation: {e}")
            raise

    def create_cash_table(self, sim=False):
        if not sim:
            table_name = 'cash'
        else:
            table_name = 'sim_cash'
        query = text(f"""
            CREATE TABLE IF NOT EXISTS gold_data_schema.{table_name} (
            date DATE PRIMARY KEY,
            free NUMERIC,
            total NUMERIC,
            ppl NUMERIC,
            result NUMERIC,
            invested NUMERIC,
            pie_cash NUMERIC,
            blocked NUMERIC,
            free_cash_pct NUMERIC,
            invested_cash_pct NUMERIC
            );
            """)
        self._execute_query(query)

    
    def create_position_table(self, sim=False):
        if not sim:
            table_name = 'positions'
        else:
            table_name = 'sim_positions'        
        query = text(f"""
        CREATE TABLE IF NOT EXISTS gold_data_schema.{table_name} (
        date DATE,
        inst_ticker VARCHAR(50),
        created_at TIMESTAMPTZ,
        quantity NUMERIC,
        quantity_available_for_trading NUMERIC,
        quantity_in_pies NUMERIC,
        current_price NUMERIC,
        average_price_paid NUMERIC,
        inst_name VARCHAR(255),
        inst_isin VARCHAR(50),
        inst_currency VARCHAR(10),
        wallet_currency VARCHAR(10),
        wallet_total_cost NUMERIC,
        wallet_current_value NUMERIC,   
        wallet_unrealized_profit_loss NUMERIC,
        wallet_fx_impact NUMERIC,
        position_wallet_share NUMERIC,
        position_roi NUMERIC,
        country_code VARCHAR(10),
        PRIMARY KEY (date, inst_ticker)
        );
        """)
        self._execute_query(query)


    
    def create_currency_table(self, sim=False):
        if not sim:
            table_name = 'currency'
        else:
            table_name = 'sim_currency'
        query = text(f"""
        CREATE TABLE IF NOT EXISTS gold_data_schema.{table_name} (
        date DATE,
        code VARCHAR(10),
        currency VARCHAR(100),
        mid NUMERIC,
        effective_date DATE,
        PRIMARY KEY (date, code)
        );
        """)
        self._execute_query(query)


    def _get_df(self, path, prefix='*.csv'):
        files = sorted(list(path.glob(prefix)))
        if not files:
            raise FileNotFoundError(f"No CSV files found in {path}")
        
        latest_file = files[-1]
        raw_data = latest_file.read_text(encoding='utf-8')
        try:
            return pd.read_csv(latest_file)
        except pd.errors.EmptyDataError as e:
            logger.error(f"CSV file is empty: {latest_file}")
            raise

    def _load_df(self, df: pd.DataFrame, table_name:str, primary_key: str):
        if df.empty:
            logger.error(f"Dataframe {table_name} is empty")
            return
        
        records = df.to_dict(orient='records')
        
        columns = ", ".join([f'"{col}"' for col in df.columns])
        placeholders = ", ".join([f":{col}" for col in df.columns])
        update_statement = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in df.columns if col not in primary_key])
        insert_query = text(f"""
                            INSERT INTO gold_data_schema.{table_name} ({columns}) 
                            VALUES ({placeholders})
                            ON CONFLICT ({primary_key}) 
                            DO UPDATE SET {update_statement};
                            """)      
        try:
            with self.sql_engine.begin() as conn:
                result = conn.execute(insert_query, records)
                logger.info(f"Data has been inserted succesfuly, rows affected: {result.rowcount}")
        
        except Exception as e: 
            logger.error(f"Failed to load Data to: {table_name}: {e}")
            raise
    
    def create_schema(self):
        query_schema = text("CREATE SCHEMA IF NOT EXISTS gold_data_schema")
        try:
            with self.sql_engine.begin() as connection:                    
                connection.execute(query_schema)
        except SQLAlchemyError as e:
            logger.error(f"Database error during schema creation: {e}")
            raise

    def load_cash(self):
        df = self._get_df(self.cash_path)
        self._load_df(df, 'cash', primary_key='date')

    def load_position(self):
        df = self._get_df(self.positions_path)
        self._load_df(df, 'positions', primary_key="date, inst_ticker")
    
    def load_currency(self):
        df = self._get_df(self.currency_path)
        self._load_df(df, 'currency', primary_key="date, code")

    def load_sim_cash(self):
        df = self._get_df(self.simulation_path, prefix='gold_sim_cash_*.csv')
        self._load_df(df, 'sim_cash', primary_key='date')

    def load_sim_position(self):
        df = self._get_df(self.simulation_path, prefix='gold_sim_positions_*.csv')
        self._load_df(df, 'sim_positions', primary_key="date, inst_ticker")
    
    def load_sim_currency(self):
        df = self._get_df(self.simulation_path, prefix='gold_sim_currency_*csv')
        self._load_df(df, 'sim_currency', primary_key="date, code")
    
   
    def load_real_data(self):
        self.create_schema()
        self.create_cash_table()
        self.create_position_table()
        self.create_currency_table()
        self.load_cash()
        self.load_position()
        self.load_currency()
    