"""Simple demo seeder for reporting tables when running the demo locally.

This script inserts minimal rows into `trades`, `hourly_reports` and
`trading_patterns` so the reporting endpoints return something sensible.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import repository


def seed_demo():
    conn = repository.pg_connect()
    try:
        now = datetime.now(timezone.utc)
        symbol = "XBTUSD"
        with conn.cursor() as cur:
            for i in range(3):
                tid = f"demo-{uuid4()}"
                ttime = now - timedelta(minutes=10 - i)
                cur.execute(
                    "INSERT INTO trades (trade_id, symbol, trade_time, price, size, side) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (tid, symbol, ttime, 30000.0 + i * 10, 100.0 + i * 50, 'Buy' if i % 2 == 0 else 'Sell'),
                )

            hour_ts = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            cur.execute(
                "INSERT INTO hourly_reports (symbol, hour_ts, trade_count, total_volume_usd, min_price, max_price, avg_price, price_std, buy_volume, sell_volume, dominant_side, computed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (symbol,hour_ts) DO NOTHING",
                (symbol, hour_ts, 3, 300000.0, 30000.0, 30020.0, 30010.0, 10.0, 200.0, 100.0, 'Buy'),
            )

            cur.execute(
                "INSERT INTO trading_patterns (symbol, hour_of_day, avg_trade_count, avg_volume_usd, avg_volatility, avg_spread, sample_hours, computed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (symbol,hour_of_day) DO NOTHING",
                (symbol, hour_ts.hour, 5.0, 500000.0, 50.0, 10.0, 24),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_demo()
