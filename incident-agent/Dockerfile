FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /project

COPY incident-agent/requirements.txt ./incident-agent/requirements.txt
RUN pip install --no-cache-dir --requirement incident-agent/requirements.txt

COPY scripts/incident-agent.py ./scripts/incident-agent.py
COPY tests/ ./tests/
RUN python -m py_compile scripts/incident-agent.py && \
    python -m unittest discover -s tests -v && \
    rm -rf tests

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY scripts/incident-agent.py ./incident-agent.py

USER 10001:10001

ENTRYPOINT ["python", "/app/incident-agent.py"]
