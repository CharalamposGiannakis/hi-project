FROM python:3.12.15-slim-bookworm

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY hi_scenario/ ./hi_scenario/
COPY infra/ ./infra/
COPY ontology/ ./ontology/
COPY examples/ ./examples/

RUN mkdir -p /data/feedback && chown 10001:10001 /data/feedback && chmod 700 /data/feedback
USER 10001:10001
CMD ["python", "-m", "uvicorn", "hi_scenario.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--root-path", "/api"]
