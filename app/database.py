import threading
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import DB_CONFIG

_local = threading.local()


def _in_transaction():
    return hasattr(_local, 'transaction_conn') and _local.transaction_conn is not None


@contextmanager
def get_db_connection():
    if hasattr(_local, 'transaction_conn') and _local.transaction_conn is not None:
        yield _local.transaction_conn
        return
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transactional():
    if hasattr(_local, 'transaction_conn') and _local.transaction_conn is not None:
        yield _local.transaction_conn
        return
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    _local.transaction_conn = conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _local.transaction_conn = None
        conn.close()


def execute_in_transaction(operations):
    with transactional() as conn:
        results = []
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for sql, params in operations:
                cur.execute(sql, params or ())
                if cur.description:
                    results.append(cur.fetchall())
                else:
                    results.append(cur.rowcount)
        return results


@contextmanager
def get_db_cursor(cursor_factory=None):
    with get_db_connection() as conn:
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()


def query(sql, params=None, fetch=True):
    with get_db_cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        if fetch:
            return cur.fetchall()
        return None


def query_one(sql, params=None):
    with get_db_cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def execute(sql, params=None):
    with get_db_cursor() as cur:
        cur.execute(sql, params or ())
        if not _in_transaction():
            cur.connection.commit()
        return cur.lastrowid


def execute_and_return_id(sql, params=None):
    with get_db_cursor() as cur:
        cur.execute(sql, params or ())
        if not _in_transaction():
            cur.connection.commit()
        result = cur.fetchone()
        return result[0] if result else None
