# Trading 212 ETL Pipeline

an automated data pipeline for extracting personal portfolio data, normalizing currencies, and loading the transformed data into a postgres database. orchestrated by apache airflow and fully dockerized.

## overview

this project extracts daily portfolio snapshots from the trading 212 api and current exchange rates from the nbp (national bank of poland) api. the data is processed through a multi-layer architecture:
1. **raw data:** original json payloads stored locally, and loaded into postgres.
2. **clean data:** flattened and standardized csv files.
3. **gold data:** final relational tables (cash, positions, currency) loaded into postgres.

## tech stack
* **python** (pandas, sqlalchemy, requests)
* **apache airflow** (orchestration & scheduling)
* **postgresql** (data warehouse)
* **docker** (containerization)

## prerequisites
to run this project, you need to have **docker** installed on your machine.

## project structure

```text 
pipeline_212/
├── dags/                  # airflow dags (production and demo)
├── src/                   # core etl logic (Extractors.py, Transformers.py, Loaders.py)
├── mock_data/             # fictional json payloads for demo execution
├── raw_data/              # ingested json files
├── clean_data/            # transformed csv files
├── gold_data/             # final csv files ready for db upload
├── compose.yaml           # docker environment setup
├── Dockerfile             # custom airflow image with requirements
├── requirements.txt       # python dependencies installed in the docker image 
└── .env.example           # template of .env file required to run the pipeline
```

to comply with trading 212 api terms of use regarding market data redistribution, this repository does not include real market data. however, you can fully test the pipeline using the demo mode with fictional data.

1. setup environment variables
create a .env file in the root directory. for the demo mode, api keys are not required, but postgres credentials must be set:
```text

PG_PASSWORD="postgres"
PG_HOST="localhost"
PG_PORT="54322"
PG_USERNAME="postgres"
PG_DB="trading_data_db"

NBP_DOMAIN="https://api.nbp.pl/api"
```
Note that PG_PORT is set to 54322 instead of standard 5432.

2. spin up the infrastructure
build and start the containers using docker compose:
```text
Bash
docker compose up -d --build
```
3. run the demo pipeline

open http://localhost:8080 in your browser (default airflow credentials: admin / admin).

locate and trigger the demo_etl_Dag.

this dag will bypass the real api calls, read structurally identical mock json files from the mock_data/ directory, and process them all the way into your postgres database.


4. run the proper pipeline

to run the pipeline with your own trading 212 account, add your real api keys to the .env file:

```text
T_212_DOMAIN="https://demo.trading212.com/api/v0"
T_212_API_KEY="your_api_key"
T_212_API_SECRET="your_api_secret"
then, trigger the etl_Dag instead of the demo version.
```
5. data transformations:

- flattening: unpacks deeply nested json structures (like walletImpact and instrument) into flat, relational database rows.

- currency normalization: gbx (pence) prices are automatically converted to gbp for consistency with polish national bank (nbp) rates.

- position wallet share calculation: calculates the exact weight of each individual asset within the entire portfolio by dividing the position's current value by the total account balance (including free cash).

- invested_cash_pct: measures overall market exposure by dividing the total invested capital by the overall account value, showing exactly how much of the portfolio is actively deployed.

- roi calculation: automatically calculates return on investment (roi) and portfolio share percentages for each position based on daily cash balance.

- country code extraction: country code is being extracted from isin number for increased readability, and easier sql joins.

## ai assistance

this project was developed using llm tools as a pair-programming partner. the core architecture, data modeling, and business logic were conceptualized and driven independently. ai was leveraged purely as an accelerator.
