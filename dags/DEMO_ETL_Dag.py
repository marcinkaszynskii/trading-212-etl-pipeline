from airflow.decorators import dag, task
from src.Extractors import Trading212Client, NBPClient
from src.Transformers import DataFormatter, DataTransformer, SimulationTransformer
from src.Loaders import SQLLoader
from src.GBM_sim import YahooExtractor, DataGenerator
from datetime import timedelta

@dag(
    dag_id="demo_etl_Dag",
    default_args= {
    'retries': 3,   
    'retry_delay': timedelta(seconds=10)
})
def demo_etl_dag():
    @task()
    def extract_212():
        extractor_212 = Trading212Client()
        extractor_212.get_mock_cash()
        extractor_212.get_mock_positions()

    @task()
    def extract_nbp():
        extractor_nbp = NBPClient()
        extractor_nbp.get_current_rates()

    @task()
    def load_raw_212():
        extractor_212 = Trading212Client()
        extractor_212.load_raw_json()

    @task()
    def load_raw_nbp():
        extractor_nbp = NBPClient()
        extractor_nbp.load_raw_json()

    @task()
    def format_currency():
        formatter = DataFormatter()
        formatter.format_currency()

    @task()
    def format_cash():
        formatter = DataFormatter()
        formatter.format_cash()

    @task()
    def format_positions():
        formatter = DataFormatter()
        formatter.format_positions()
    
    @task()
    def transform_cash():
        transformer = DataTransformer()
        transformer.transform_cash()

    @task()
    def transform_positions():
        transformer = DataTransformer()
        transformer.transform_positions()       

    @task()
    def transform_currency():
        transformer = DataTransformer()
        transformer.transform_currency()

    @task()
    def get_historical_data():
        yahoo_extractor = YahooExtractor()
        yahoo_extractor.get_historical_data()

    @task
    def generate_sim_data():
        data_generator = DataGenerator()
        data_generator.generate_data()

    @task
    def transform_sim_data():
        sim_transformer = SimulationTransformer()
        sim_transformer.run_sim_transformation_pipeline()

    @task()
    def create_schema():
        loader = SQLLoader()
        loader.create_schema()

    @task()
    def create_cash_table():
        loader = SQLLoader()
        loader.create_cash_table(sim=True)

    @task()
    def create_position_table():
        loader = SQLLoader()
        loader.create_position_table(sim=True)
    
    @task()
    def create_currency_table():
        loader = SQLLoader()
        loader.create_currency_table(sim=True)

    @task()
    def load_sim_cash():
        loader = SQLLoader()
        loader.load_sim_cash()

    @task()
    def load_sim_positions():
        loader = SQLLoader()
        loader.load_sim_position()

    @task()
    def load_sim_currency():
        loader = SQLLoader()
        loader.load_sim_currency()


    t_extract_212 = extract_212()
    t_extract_nbp = extract_nbp()
    t_load_raw_212 = load_raw_212()
    t_load_raw_nbp = load_raw_nbp()

    t_format_cash = format_cash()
    t_format_pos = format_positions()
    t_format_curr = format_currency()
    
    t_transform_curr = transform_currency()
    t_transform_cash = transform_cash()
    t_transform_pos = transform_positions()

    t_get_hist_data = get_historical_data()
    t_gen_sim_data = generate_sim_data()
    t_transform_sim_data = transform_sim_data()

    t_create_schema = create_schema()
    t_create_cash_tbl = create_cash_table()
    t_create_pos_tbl = create_position_table()
    t_create_curr_tbl = create_currency_table()
    t_load_sim_cash = load_sim_cash()
    t_load_sim_pos = load_sim_positions()
    t_load_sim_curr = load_sim_currency()


    t_extract_212 >> t_load_raw_212
    t_extract_nbp >> t_load_raw_nbp

    t_extract_212 >> [t_format_cash, t_format_pos]
    t_extract_nbp >> t_format_curr 

    t_format_cash >> t_transform_cash
    t_format_pos >> t_transform_pos
    t_format_curr >> t_transform_curr

    t_transform_pos >> t_get_hist_data
    t_get_hist_data >> t_gen_sim_data
    t_gen_sim_data >> t_transform_sim_data

    t_create_schema >> [t_create_cash_tbl, t_create_pos_tbl, t_create_curr_tbl]

    t_create_cash_tbl >> t_load_sim_cash
    t_create_pos_tbl >> t_load_sim_pos
    t_create_curr_tbl >> t_load_sim_curr

    t_transform_sim_data >> [t_load_sim_pos, t_load_sim_cash, t_load_sim_curr]

demo_etl_dag()


