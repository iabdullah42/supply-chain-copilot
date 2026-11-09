"""Generate a synthetic procurement database: suppliers, purchase orders and shipments.

Covers calendar year 2025 for a consumer-goods company. Saved as a SQLite file
(data/supply_chain.db), a database that lives in one file and is built into Python.
All names and numbers are invented.
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 11
AS_OF = pd.Timestamp("2025-12-31")   # "today" in this dataset

# (supplier, country, category, promised lead time in days, on-time reliability)
SUPPLIERS = [
    ("Apex Polymers", "USA", "Packaging", 10, 0.95),
    ("BlueRiver Packaging", "USA", "Packaging", 12, 0.90),
    ("Cobalt Bottling", "Mexico", "Packaging", 18, 0.78),
    ("Delta Label Co", "USA", "Packaging", 7, 0.97),
    ("Everfresh Ingredients", "USA", "Ingredients", 14, 0.92),
    ("Granite Foods", "Canada", "Ingredients", 16, 0.88),
    ("Harbor Spice Traders", "India", "Ingredients", 45, 0.70),
    ("Iris Botanicals", "Vietnam", "Ingredients", 40, 0.74),
    ("Juniper Chemicals", "Germany", "Chemicals", 35, 0.90),
    ("Keystone Solvents", "USA", "Chemicals", 12, 0.85),
    ("Lumen Cartons", "China", "Packaging", 42, 0.68),
    ("Meridian Sweeteners", "Brazil", "Ingredients", 38, 0.80),
]
CARRIERS = {"USA": ["UPS Freight", "XPO", "Estes"], "Canada": ["XPO", "Estes"], "Mexico": ["XPO", "Estes"],
            "overseas": ["Maersk", "MSC", "Hapag-Lloyd"]}


def build(seed: int = SEED, n_pos: int = 2400) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    suppliers = pd.DataFrame(SUPPLIERS, columns=["name", "country", "category", "promised_lead_days", "reliability"])
    suppliers.insert(0, "supplier_id", [f"S{i + 1:02d}" for i in range(len(suppliers))])

    # Purchase orders spread over 2025; bigger, steadier suppliers get more orders.
    weights = 0.5 + suppliers["reliability"].to_numpy()
    sup_idx = rng.choice(len(suppliers), size=n_pos, p=weights / weights.sum())
    order_date = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, n_pos), unit="D")
    s = suppliers.iloc[sup_idx].reset_index(drop=True)
    promised = order_date + pd.to_timedelta(s["promised_lead_days"], unit="D")

    unit_cost = np.round(rng.lognormal(np.log(4), 0.6, n_pos), 2)
    qty = (rng.integers(5, 60, n_pos) * 100).astype(int)
    pos = pd.DataFrame({
        "po_id": [f"PO{i + 1:05d}" for i in range(n_pos)],
        "supplier_id": s["supplier_id"],
        "category": s["category"],
        "order_date": order_date,
        "promised_date": promised,
        "quantity": qty,
        "unit_cost": unit_cost,
        "po_value": np.round(qty * unit_cost, 2),
    })

    # Delivery: reliable suppliers arrive near the promise; others run late, overseas lanes more so.
    late = rng.random(n_pos) > s["reliability"].to_numpy()
    overseas = ~s["country"].isin(["USA", "Canada", "Mexico"]).to_numpy()
    delay = np.where(late, rng.gamma(2.0, np.where(overseas, 6.0, 2.5)), -rng.integers(0, 3, n_pos))
    # Q4 port congestion adds delay to overseas lanes.
    q4 = np.asarray(order_date.month >= 9)
    delay = delay + np.where(overseas & q4 & late, rng.integers(3, 10, n_pos), 0)
    received = promised + pd.to_timedelta(np.round(delay).astype(int), unit="D")

    carrier = [rng.choice(CARRIERS["overseas"] if o else CARRIERS[c]) for o, c in zip(overseas, s["country"])]
    short = rng.random(n_pos) < np.where(late, 0.12, 0.03)            # some deliveries arrive short
    received_qty = np.where(short, (qty * rng.uniform(0.8, 0.98, n_pos)).astype(int), qty)
    freight = np.round(pos["po_value"] * np.where(overseas, 0.09, 0.04) * rng.uniform(0.8, 1.2, n_pos), 2)

    is_open = received > AS_OF                                       # not yet arrived "today"
    shipments = pd.DataFrame({
        "po_id": pos["po_id"],
        "carrier": carrier,
        "received_date": received.where(~is_open),
        "received_qty": np.where(is_open, np.nan, received_qty),
        "freight_cost": freight,
    })
    pos["status"] = np.where(is_open, "open", "received")
    return {"suppliers": suppliers.drop(columns="reliability"), "purchase_orders": pos, "shipments": shipments}


def save(tables: dict[str, pd.DataFrame], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as con:
        for name, df in tables.items():
            out = df.copy()
            for col in out.select_dtypes("datetime").columns:
                out[col] = out[col].dt.strftime("%Y-%m-%d")      # store dates as YYYY-MM-DD text
            out.to_sql(name, con, index=False)


if __name__ == "__main__":
    db = Path(__file__).resolve().parents[1] / "data" / "supply_chain.db"
    tables = build()
    save(tables, db)
    print(f"Saved {db}")
    for name, df in tables.items():
        print(f"  {name:16s} {len(df):5,} rows")
    with sqlite3.connect(db) as con:
        print(pd.read_sql("""
            SELECT s.name, COUNT(*) AS pos,
                   ROUND(100.0 * AVG(sh.received_date <= p.promised_date), 1) AS on_time_pct
            FROM purchase_orders p
            JOIN suppliers s  ON s.supplier_id = p.supplier_id
            JOIN shipments sh ON sh.po_id = p.po_id
            WHERE p.status = 'received'
            GROUP BY s.name ORDER BY on_time_pct
            LIMIT 3""", con))