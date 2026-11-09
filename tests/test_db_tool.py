import sqlite3

import pytest

from src.db_tool import DB_PATH, check_query, run_sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM purchase_orders",
    "UPDATE suppliers SET name = 'x'",
    "DROP TABLE shipments",
    "SELECT 1; DROP TABLE suppliers",
    "INSERT INTO suppliers VALUES ('S99', 'x', 'x', 'x', 1)",
    "PRAGMA table_info(suppliers)",
])
def test_anything_but_a_single_select_is_blocked(sql):
    assert check_query(sql) is not None
    assert run_sql(sql).startswith("ERROR")


def test_select_and_with_queries_are_allowed():
    assert check_query("SELECT * FROM suppliers") is None
    assert check_query("WITH x AS (SELECT 1 AS n) SELECT n FROM x") is None


def test_results_come_back_as_csv():
    out = run_sql("SELECT COUNT(*) AS n FROM purchase_orders WHERE status = 'open'")
    assert out.strip().splitlines() == ["n", "151"]


def test_sql_errors_are_returned_not_raised():
    assert run_sql("SELECT * FROM no_such_table").startswith("ERROR")


def test_large_results_are_truncated():
    out = run_sql("SELECT po_id FROM purchase_orders")
    assert "showing first 200 of 2400 rows" in out


def test_database_still_intact():
    with sqlite3.connect(DB_PATH) as con:
        assert con.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0] == 2400
