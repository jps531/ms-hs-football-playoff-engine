# ms-hs-football-playoff-engine

A web application that calculates standings and playoff scenarios for Mississippi High School Football.

`docker compose --env-file .env.local down`
`docker compose --env-file .env.local up --build -d`

## Setting Up Your Environment

1. Navigate to [the Local Prefect UI](http://localhost:4200/deployments)
2. Do a "Quick Run" of the **Regions Data Pipeline**
3. Do a "Quick Run" of the **MaxPreps Data Pipeline**
4. Do a "Quick Run" of the **School Info Data Pipeline**
5. 4. Do a "Quick Run" of the **AHSFHS Schedule Data Pipeline**