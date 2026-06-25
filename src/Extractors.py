import requests 
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import base64
import os    
from dotenv import load_dotenv
import time  
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus
import json  
import logging
from pathlib import Path

load_dotenv()
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent

class Trading212Client:
    def __init__(self):
        """
        expects .env variables: PG_USERNAME, PG_PASSWORD, PG_PORT, PG_HOST, PG_DB,
        variables  T_212_DOMAIN, T_212_API_KEY, T_212_API_SECRET are required for real data extraction.
        """
        self.domain = os.getenv('T_212_DOMAIN')
        self.api_key = os.getenv('T_212_API_KEY')
        self.api_secret = os.getenv('T_212_API_SECRET')
        
        '''        try:
            self.headers = self._generate_headers()
        except Exception as e:
            self.headers = {}
            logger.info(f"Failed to generate Trading212 headers, only demo version is available. {e}")
        '''

        self.session = self._create_session()
        try:
            self.session.headers.update(self._generate_headers())
        except Exception as e:
            self.headers = {}
            logger.info(f"Failed to generate Trading212 headers, only demo version is available. {e}")

        self.pg_username = os.getenv('PG_USERNAME')
        self.pg_password = os.getenv('PG_PASSWORD')
        self.pg_port = os.getenv('PG_PORT')
        self.pg_host = os.getenv('PG_HOST')
        self.pg_db = os.getenv('PG_DB')
    
        self.output_folder = PROJECT_DIR / 'raw_data' / 'raw_trading_data'

        self.output_folder.mkdir(parents=True, exist_ok=True)       

        self.sql_engine = self._create_sql_engine() 

    def _generate_headers(self):
        credentials_string = f'{self.api_key}:{self.api_secret}'
        encoded_credentials = base64.b64encode(credentials_string.encode('utf-8')).decode('utf-8')
        auth_header = f"Basic {encoded_credentials}"
        headers = {'Authorization':auth_header,
                'accept': 'application/json'}
        return headers
    
    def _create_session(self):
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def _connection_engine(self, path):
        url = f"{self.domain}/{path}"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
    
        except requests.exceptions.Timeout:
            logger.error(f"Timeout: server did not respond in time (10s): {url}")
            raise
        except requests.exceptions.HTTPError as http_err:
            logger.error(f'HTTP error: {http_err}')
            raise
        except requests.exceptions.ConnectionError as conn_err:
            logger.error((f'Connection error: {conn_err}'))
            raise 

    def _create_sql_engine(self):
        return create_engine(f"postgresql://{self.pg_username}:\
{quote_plus(self.pg_password)}@{self.pg_host}:{self.pg_port}/{self.pg_db}")
        

    def _create_date_str(self):
        return time.strftime('%Y-%m-%d', time.localtime())
    
    def _save_json(self, data, prefix):
        date_str = self._create_date_str()
        dir_path = self.output_folder / prefix 
        dir_path.mkdir(parents=True, exist_ok=True)       
        file_path = dir_path / f"{prefix}_{date_str}.json"
        with file_path.open("w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        
    def _create_table(self):
        query_schema = text("CREATE SCHEMA IF NOT EXISTS bronze_data_schema")
        query = text("""
        CREATE TABLE IF NOT EXISTS bronze_data_schema.raw_212 (
        date TIMESTAMPTZ PRIMARY KEY,
        position JSON,
        cash JSON
        );
        """)             
        try:
            with self.sql_engine.begin() as connection:
                
                connection.execute(query_schema)
                connection.execute(query)
        except Exception as e:
            logger.error(f"Connection error {e}")
            raise

    def get_summary(self):
        path = "equity/account/summary"
        prefix = "raw_summary_data"
        date_str = self._create_date_str()
        data = self._connection_engine(path=path)
        self._save_json(data=data, prefix=prefix)
     
    def get_cash(self):
        path = "equity/account/cash"
        prefix = "raw_cash_data"
        date_str = self._create_date_str()
        data = self._connection_engine(path=path)
        self._save_json(data=data, prefix=prefix)


    def get_positions(self):
        path = "equity/positions"
        prefix = "raw_positions_data"
        date_str = self._create_date_str()
        data = self._connection_engine(path=path)
        self._save_json(data=data, prefix=prefix)

    
    def get_mock_positions(self):
        """
        gets mock positions data in case of not having api key
        """
        prefix = "raw_positions_data"
        file_path = PROJECT_DIR / 'mock_data' / 'mock_positions.json'
        raw_data = file_path.read_text(encoding='utf-8')
        data = json.loads(raw_data)
        self._save_json(data=data, prefix=prefix)

    def get_mock_cash(self):
        """
        gets mock cash data in case of not having api key
        """
        prefix = "raw_cash_data"
        file_path = PROJECT_DIR / 'mock_data' / 'mock_cash.json'
        raw_data = file_path.read_text(encoding='utf-8')
        data = json.loads(raw_data)
        self._save_json(data=data, prefix=prefix)
    


    def load_raw_json(self):
        """
        Loads local raw JSON data into the bronze schema.
        Requires get_positions() and get_cash() to be executed first.
        """
        date_str = self._create_date_str()
        pos_path = self.output_folder / f"raw_positions_data/raw_positions_data_{date_str}.json"
        cash_path = self.output_folder / f"raw_cash_data/raw_cash_data_{date_str}.json"
        try:
            with open(pos_path, 'r', encoding='utf-8') as f:
                raw_position_json = json.load(f)
            with open(cash_path, 'r', encoding='utf-8') as f:
                raw_cash_json = json.load(f)    
        except FileNotFoundError as e:
            logger.error(f"Required raw data files not found. Did you run API fetchers? {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON files: {e}")
            raise
        query = text(f"""
        INSERT INTO bronze_data_schema.raw_212 (date, position, cash)
        VALUES (:date, :position, :cash)
        ON CONFLICT (date) DO NOTHING;
        """)
        self._create_table()        
        try:
            with self.sql_engine.begin() as connection:
                connection.execute(query, {
                    'date':date_str,
                    'position':json.dumps(raw_position_json),
                    'cash':json.dumps(raw_cash_json)
                })
        except SQLAlchemyError as e:
            logger.error(f"Database insertion error: {e}")
            raise
        


class NBPClient:
    def __init__(self):
        """
        expects .env variables: NBP_DOMAIN, 
        PG_USERNAME, PG_PASSWORD, PG_PORT, PG_HOST, PG_DB
        """
        self.domain = os.getenv('NBP_DOMAIN')
        
        self.output_folder = PROJECT_DIR / 'raw_data' / 'raw_currency_data'

        self.pg_username = os.getenv('PG_USERNAME')
        self.pg_password = os.getenv('PG_PASSWORD')
        self.pg_port = os.getenv('PG_PORT')
        self.pg_host = os.getenv('PG_HOST')
        self.pg_db = os. getenv('PG_DB')
        
        self.sql_engine = self._create_sql_engine()
    
        os.makedirs(self.output_folder, exist_ok=True)

    def _connection_engine(self, path):
        url = f"{self.domain}/{path}"
        headers = {'Accept': 'application/json'}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logger.error(f'HTTP error: {http_err}')
            raise
        except requests.exceptions.ConnectionError as conn_err:
            logger.error((f'Connection error: {conn_err}'))
            raise 

    def _create_date_str(self):
        return time.strftime('%Y-%m-%d', time.localtime())

    def _create_sql_engine(self):
        return create_engine(f"postgresql://{self.pg_username}:\
{quote_plus(self.pg_password)}@{self.pg_host}:{self.pg_port}/{self.pg_db}")
        
    def _save_json(self, data, prefix, date_str):
        file_path = self.output_folder / f"{prefix}_{date_str}.json"
        with file_path.open("w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _create_table(self):
        query_schema = text("CREATE SCHEMA IF NOT EXISTS bronze_data_schema")
        query = text("""
        CREATE TABLE IF NOT EXISTS bronze_data_schema.raw_nbp (
        date TIMESTAMPTZ PRIMARY KEY,
        currency_data JSON
        );
        """)             
        try:
            with self.sql_engine.begin() as connection:
                connection.execute(query_schema)
                connection.execute(query)
        except Exception as e:
            logger.error(f"Connection error {e}")
            raise

    def get_current_rates(self):
        data = self._connection_engine('exchangerates/tables/a/')
        # during the weekend or in the early day hours 
        # the actual rate date may differ from the current date.
        self.effective_date_str = data[0].get('effectiveDate')
        self._save_json(data=data, prefix='raw_currency_data', date_str=self.effective_date_str)

    def load_raw_json(self):
        """
        Requires raw_currency_data file with the effective date in the directory.
        """
        files = sorted(list(self.output_folder.glob('raw_currency_data_*.json')))
        if not files:
            raise FileNotFoundError(f"No JSON files found in {self.output_folder}")
        latest_file = files[-1]
        effective_date_str = latest_file.stem[-10:]

        try:
            with latest_file.open('r', encoding='utf-8') as f:
                raw_currency_data = json.load(f)
        except (FileNotFoundError) as e:
            logger.error(f"Error loading local currency JSON: {e}")
            raise

        query = text(f"""
        INSERT INTO bronze_data_schema.raw_nbp (date, currency_data)
        VALUES (:date, :currency_data)
        ON CONFLICT (date) DO NOTHING;
        """)
        self._create_table()        
        try:
            with self.sql_engine.begin() as connection:
                connection.execute(query, {
                    'date':effective_date_str,
                    'currency_data':json.dumps(raw_currency_data)
                })
        except Exception as e:
            logger.error(f"Connection error {e}")
            raise
