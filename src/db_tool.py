"""A safe, read-only SQL tool for the assistant.

Claude never touches the database directly. It sends a query; this code checks it,
runs it on a READ-ONLY connection, and returns the rows as text.
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "supply_chain.db"
MAX_ROWS = 200

SCHEMA = """
Tables (SQLite). Dates are TEXT 'YYYY-MM-DD'. Today (as of) is 2025-12-31.

suppliers(supplier_id, name, country, category, promised_lead_days)
purchase_orders(po_id, supplier_id, category, order_date, promised_date, quantity,
                unit_cost, po_value, status)   -- status: 'received' or 'open'
shipments(po_id, carrier, received_date, received_qty, freight_cost)
                -- one row per PO; received_date and received_qty are NULL while the PO is open

Joins: purchase_orders.supplier_id = suppliers.supplier_id; shipments.po_id = purchase_orders.po_id
"""

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma|vacuum)\b", re.I)


def check_query(sql: str) -> str | None:
    """Return an error message if the query is not allowed, else None."""
    statement = sql.strip().rstrip(";")
    if ";" in statement:
        return "Only one statement is allowed."
    if not re.match(r"^\s*(select|with)\b", statement, re.I):
        return "Only SELECT queries are allowed."
    if FORBIDDEN.search(statement):
        return "Query contains a forbidden keyword; this tool is read-only."
    return None


def run_sql(sql: str, db_path: Path = DB_PATH) -> str:
    """Run a read-only query and return the result as text (or an error message)."""
    problem = check_query(sql)
    if problem:
        return f"ERROR: {problem}"
    try:
        # mode=ro opens the file read-only, so even a query that slipped past the check cannot change data.
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as con:
            df = pd.read_sql(sql, con)
    except Exception as exc:  # noqa: BLE001 - send any SQL error back so Claude can fix its query
        return f"ERROR: {exc}"
    note = ""
    if len(df) > MAX_ROWS:
        note = f"\n(showing first {MAX_ROWS} of {len(df)} rows - aggregate or add LIMIT)"
        df = df.head(MAX_ROWS)
    return df.to_csv(index=False) + note