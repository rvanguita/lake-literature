"""Airflow DAGs for the lake-literature medallion pipeline.

Six DAGs, matching the six stage buttons in the Streamlit dashboard 1:1:
`lake_literature_raw/bronze/silver/gold/embed` (one task each) and
`lake_literature_all` (five chained tasks). Every task just shells out to
the same `uv run lake-literature --stage <stage>` entrypoint the CLI uses --
this file intentionally does not import `lake_literature` directly, so the
pipeline logic (ingest/transform/pipeline.py) needs zero changes to be
orchestrated by Airflow.

All DAGs are `schedule=None` -- manual/API trigger only, no cron schedule --
since the pipeline is meant to be run on demand from the dashboard.
"""

from __future__ import annotations

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = "/opt/airflow/project"
START_DATE = pendulum.datetime(2024, 1, 1, tz="UTC")

STAGES = ("raw", "bronze", "silver", "gold", "embed")


def _bash_command(stage: str) -> str:
    return f"cd {PROJECT_DIR} && uv run lake-literature --stage {stage}"


default_args = {
    "owner": "lake-literature",
    "retries": 0,
}

# One single-task DAG per stage, mirroring the dashboard's individual buttons.
for stage in STAGES:
    with DAG(
        dag_id=f"lake_literature_{stage}",
        description=f"Run the {stage} stage of the lake-literature medallion pipeline.",
        schedule=None,
        start_date=START_DATE,
        catchup=False,
        default_args=default_args,
        tags=["lake-literature"],
    ):
        BashOperator(task_id=stage, bash_command=_bash_command(stage))

# One combined DAG chaining all four stages in order, for the "run all" button.
with DAG(
    dag_id="lake_literature_all",
    description="Run the full lake-literature medallion pipeline: raw->bronze->silver->gold.",
    schedule=None,
    start_date=START_DATE,
    catchup=False,
    default_args=default_args,
    tags=["lake-literature"],
):
    tasks = [BashOperator(task_id=stage, bash_command=_bash_command(stage)) for stage in STAGES]
    for upstream, downstream in zip(tasks, tasks[1:], strict=False):
        upstream >> downstream
