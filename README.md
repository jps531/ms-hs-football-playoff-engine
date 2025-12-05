# ms-hs-football-playoff-engine

A web application that calculates standings and playoff scenarios for Mississippi High School Football.

`docker compose --env-file .env.local down`
`docker compose --env-file .env.local up --build -d`

## Setting Up Your Environment

1. Navigate to [the Local Prefect UI](http://localhost:4200/deployments)
2. Do a "Quick Run" of the **Regions Data Pipeline**
3. Do a "Quick Run" of the **MaxPreps Data Pipeline**
4. Do a "Quick Run" of the **School Info Data Pipeline**
5. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline**

## Debugging

Run all region scenarios:

`python enumerate_all_regions_scenarios.py --season 2025 --dsn "postgresql://postgres:postgres@0.0.0.0:5432/mshsfootball"`

Run a specific region scenario:

`python simulate_region_finish.py \                                                                 
  --class 1 --region 8 --season 2025 \
  --dsn "postgresql://postgres:postgres@0.0.0.0:5432/mshsfootball" \
  --out-scenarios "scenarios.txt"`

## Testing

Run the following tests:

`source .venv/bin/activate`
`cd prefect_files`
`pip install -r requirements.txt`
`pytest -vv`