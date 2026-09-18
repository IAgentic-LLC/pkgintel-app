# Chapter 13: Airflow gets its own image, its own containers, its own
# lifecycle, deliberately separate from pkgintel-app's own uv-managed
# venv. Airflow's own dependency constraints are notoriously strict;
# running it as its own service, talking to this project's code over
# a mounted PYTHONPATH rather than a shared virtualenv, is the real,
# common way teams actually run it, not a shortcut.
FROM apache/airflow:3.3.2

# Same real, live finding as chapter 10's Dockerfile: reliable-agents-labs
# is a git dependency, and this base image has no git binary either.
# Applied here on purpose this time, not rediscovered.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER airflow

# A real, live-found bug: installing extra packages with a bare
# `pip install -r requirements.txt` let pip drift some shared
# transitive dependency out from under Airflow's own pinned versions,
# breaking its internal API-versioning machinery (cadwyn) with a 500
# on every single task execution call. Airflow's own constraints file
# is the documented, correct fix: it pins everything Airflow itself
# depends on, leaving genuinely new packages (neo4j, qdrant-client,
# reliable-agents-labs) free to resolve normally.
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.13.txt" \
    -r /requirements.txt

# reliable-agents-labs' own pyproject.toml declares FastAPI, LangGraph,
# uvicorn, none of which the DAG's actual imports (pypi.py, models.py,
# vector_store.py, graph_store.py, ingest.py) ever touch, and its
# FastAPI floor collides with Airflow's own pinned version, confirmed
# live by the exact same constraint-resolution failure the base
# requirements just avoided. --no-deps installs the package itself
# without pulling in a dependency list it doesn't need here.
RUN pip install --no-cache-dir --no-deps \
    "git+https://github.com/Sebuliba-Adrian/reliable-agents-labs.git"
