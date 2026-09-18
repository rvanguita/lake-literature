"""Small REST client for the Airflow webserver (Airflow 3, API v2).

The dashboard triggers DAG runs and polls their status through this client
instead of running the pipeline in-process. Auth: with
`AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True` set on the Airflow
service (see docker-compose.yml), `GET /auth/token` with no credentials
returns a valid admin JWT -- appropriate for this single-user local setup,
avoids distributing a password between containers.
"""

from __future__ import annotations

import requests

from lake_research_map.config import get_airflow_base_url

_TIMEOUT = 15  # seconds; these are small metadata calls, not pipeline runs


class AirflowError(RuntimeError):
    """Raised when the Airflow webserver is unreachable or returns an error."""


def _base_url() -> str:
    return get_airflow_base_url().rstrip("/")


def get_token() -> str:
    try:
        resp = requests.get(f"{_base_url()}/auth/token", timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AirflowError(f"could not reach Airflow at {_base_url()}: {exc}") from exc
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise AirflowError(f"unexpected /auth/token response: {data}")
    return token


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}


def trigger_dag(dag_id: str) -> str:
    """Trigger a new run of `dag_id`. Returns the new dag_run_id."""
    url = f"{_base_url()}/api/v2/dags/{dag_id}/dagRuns"
    try:
        resp = requests.post(url, headers=_headers(), json={"logical_date": None}, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AirflowError(f"failed to trigger DAG {dag_id!r}: {exc}") from exc
    data = resp.json()
    dag_run_id = data.get("dag_run_id")
    if not dag_run_id:
        raise AirflowError(f"unexpected trigger response for {dag_id!r}: {data}")
    return dag_run_id


def get_dag_run(dag_id: str, dag_run_id: str) -> dict:
    """Return the DAG run's metadata, including its `state`."""
    url = f"{_base_url()}/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AirflowError(f"failed to fetch run {dag_id}/{dag_run_id}: {exc}") from exc
    return resp.json()


def get_task_instances(dag_id: str, dag_run_id: str) -> list[dict]:
    """Return per-task status for a DAG run (empty list on any failure)."""
    url = f"{_base_url()}/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
    try:
        resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    return resp.json().get("task_instances", [])
