from .connection import get_connection


def search_runs(
    status: str | None = None,
    limit: int = 10,
):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if status is None:
                cursor.execute(
                    """
                    SELECT run_id, user_id, status, created_at
                    FROM runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT run_id, user_id, status, created_at
                    FROM runs
                    WHERE status = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (status, limit),
                )

            return cursor.fetchall()


def get_run(run_id: str):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, user_id, status, created_at, updated_at
                FROM runs
                WHERE run_id = %s
                """,
                (run_id,),
            )

            return cursor.fetchone()


def get_traces(run_id: str):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT trace_id, run_id, message, created_at
                FROM traces
                WHERE run_id = %s
                ORDER BY created_at
                """,
                (run_id,),
            )

            return cursor.fetchall()