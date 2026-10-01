import psycopg
from psycopg.rows import dict_row


def get_connection():
    return psycopg.connect(
        host="localhost",
        port=5432,
        dbname="agent_db",
        user="postgres",
        password="postgres",
        row_factory=dict_row,
    )