import asyncio
from datetime import datetime, timedelta

from mcp_servers import postgres_server
from postgres import queries


class FakeCursor:
    def __init__(self, runs, traces):
        self.runs = runs
        self.traces = traces
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params):
        if "FROM traces" in query:
            run_id = params[0]
            self.rows = sorted(
                (trace for trace in self.traces if trace["run_id"] == run_id),
                key=lambda trace: trace["created_at"],
            )
        elif "WHERE status = %s" in query:
            status, limit = params
            self.rows = sorted(
                (run for run in self.runs if run["status"] == status),
                key=lambda run: run["created_at"],
                reverse=True,
            )[:limit]
        elif "WHERE run_id = %s" in query:
            run_id = params[0]
            self.rows = [run for run in self.runs if run["run_id"] == run_id]
        else:
            limit = params[0]
            self.rows = sorted(
                self.runs,
                key=lambda run: run["created_at"],
                reverse=True,
            )[:limit]

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, runs, traces):
        self.runs = runs
        self.traces = traces

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return FakeCursor(self.runs, self.traces)


def use_fake_postgres(monkeypatch):
    now = datetime(2026, 1, 1)
    runs = [
        {
            "run_id": "run-1",
            "user_id": "user-1",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
        },
        {
            "run_id": "run-2",
            "user_id": "user-2",
            "status": "failed",
            "created_at": now + timedelta(minutes=1),
            "updated_at": now + timedelta(minutes=1),
        },
        {
            "run_id": "run-3",
            "user_id": "user-3",
            "status": "failed",
            "created_at": now + timedelta(minutes=2),
            "updated_at": now + timedelta(minutes=2),
        },
    ]
    traces = [
        {
            "trace_id": "trace-2",
            "run_id": "run-2",
            "message": "second",
            "created_at": now + timedelta(seconds=2),
        },
        {
            "trace_id": "trace-other",
            "run_id": "run-1",
            "message": "other run",
            "created_at": now,
        },
        {
            "trace_id": "trace-1",
            "run_id": "run-2",
            "message": "first",
            "created_at": now + timedelta(seconds=1),
        },
    ]
    monkeypatch.setattr(
        queries,
        "get_connection",
        lambda: FakeConnection(runs, traces),
    )
    return runs


def test_search_runs_without_status_returns_multiple_runs_up_to_limit(monkeypatch):
    use_fake_postgres(monkeypatch)

    result = queries.search_runs(status=None, limit=2)

    assert [run["run_id"] for run in result] == ["run-3", "run-2"]


def test_search_runs_with_status_returns_only_failed_runs(monkeypatch):
    use_fake_postgres(monkeypatch)

    result = queries.search_runs(status="failed")

    assert [run["run_id"] for run in result] == ["run-3", "run-2"]
    assert all(run["status"] == "failed" for run in result)


def test_get_run_returns_existing_run(monkeypatch):
    runs = use_fake_postgres(monkeypatch)

    assert queries.get_run("run-2") == runs[1]


def test_get_run_returns_none_for_missing_run(monkeypatch):
    use_fake_postgres(monkeypatch)

    assert queries.get_run("missing") is None


def test_get_traces_returns_only_requested_run_in_created_at_order(monkeypatch):
    use_fake_postgres(monkeypatch)

    result = queries.get_traces("run-2")

    assert [trace["trace_id"] for trace in result] == ["trace-1", "trace-2"]


def test_postgres_mcp_server_registers_run_tools():
    tools = asyncio.run(postgres_server.mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "search_runs",
        "get_run",
        "get_traces",
    }
