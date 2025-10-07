FROM python:3.11-slim

# System deps for pandas/lxml/psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libpq-dev libxml2-dev libxslt1.1 libxslt1-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY flow.py /app/
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1

# Default: do nothing—worker will run the deployment by schedule.
CMD ["/bin/bash", "-lc", "/app/entrypoint.sh"]