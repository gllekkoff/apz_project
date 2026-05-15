from datetime import datetime
import os
from typing import Optional

import psycopg2
import psycopg2.extras

PG_DSN = os.getenv("POSTGRES_DSN")


def pg_connect():
    last_exc = None
    for _ in range(30):
        try:
            conn = psycopg2.connect(PG_DSN)
            conn.autocommit = False
            return conn
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Postgres not reachable: {last_exc}")


def get_hourly_reports(symbol: str, hours: int):
    sql = """
    SELECT symbol, hour_ts, trade_count, total_volume_usd,
           min_price, max_price, avg_price, price_std,
           buy_volume, sell_volume, dominant_side
    FROM hourly_reports
    WHERE symbol = %s
      AND hour_ts >= date_trunc('hour', now()) - %s::interval
      AND hour_ts <  date_trunc('hour', now())
    ORDER BY hour_ts DESC
    """
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (symbol, f"{hours} hours"))
            return cur.fetchall()


def get_trading_patterns(symbol: str):
    sql = """
    SELECT hour_of_day, avg_trade_count, avg_volume_usd,
           avg_volatility, avg_spread, sample_hours, computed_at
    FROM trading_patterns
    WHERE symbol = %s
    ORDER BY hour_of_day
    """
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (symbol,))
            return cur.fetchall()


_PERIOD_MAP = {"1h": "1 hour", "6h": "6 hours", "12h": "12 hours", "24h": "24 hours", "7d": "7 days"}


def get_whale_impact(symbol: Optional[str], period: str):
    pg_interval = _PERIOD_MAP.get(period)
    if pg_interval is None:
        raise ValueError(f"unsupported period '{period}'; allowed: {list(_PERIOD_MAP)}")

    sql = """
        WITH window_bounds AS (
            SELECT now() - %(period)s::interval AS period_start, now() AS period_end
        ),
        threshold AS (
            SELECT symbol, percentile_cont(0.9) WITHIN GROUP (ORDER BY size) AS p90
            FROM trades, window_bounds
            WHERE trade_time >= window_bounds.period_start
              AND (%(symbol)s::text IS NULL OR symbol = %(symbol)s)
            GROUP BY symbol
        ),
        large_trades AS (
            SELECT t.trade_id, t.symbol, t.trade_time, t.price, t.size, t.side
            FROM trades t
            JOIN threshold th ON t.symbol = th.symbol
            JOIN window_bounds wb ON true
            WHERE t.size > th.p90
              AND t.trade_time >= wb.period_start
              AND t.trade_time <= wb.period_end - interval '5 minutes'
        ),
        impacts AS (
            SELECT
                lt.symbol, lt.trade_id, lt.trade_time, lt.price, lt.size, lt.side,
                (SELECT avg(t2.price) FROM trades t2
                  WHERE t2.symbol = lt.symbol
                    AND t2.trade_time >= lt.trade_time - interval '5 minutes'
                    AND t2.trade_time <  lt.trade_time) AS avg_before,
                (SELECT avg(t2.price) FROM trades t2
                  WHERE t2.symbol = lt.symbol
                    AND t2.trade_time >  lt.trade_time
                    AND t2.trade_time <= lt.trade_time + interval '5 minutes') AS avg_after
            FROM large_trades lt
        )
        SELECT
            impacts.symbol,
            count(*)::bigint                                                AS large_trade_count,
            avg(size)::double precision                                     AS avg_large_trade_size,
            (SELECT p90 FROM threshold WHERE threshold.symbol = impacts.symbol) AS p90_threshold,
            avg(CASE WHEN avg_before > 0
                     THEN (avg_after - avg_before) / avg_before * 100 END)::double precision AS avg_impact_pct,
            avg(CASE WHEN side = 'Buy'  AND avg_before > 0
                     THEN (avg_after - avg_before) / avg_before * 100 END)::double precision AS avg_buy_impact_pct,
            avg(CASE WHEN side = 'Sell' AND avg_before > 0
                     THEN (avg_after - avg_before) / avg_before * 100 END)::double precision AS avg_sell_impact_pct
        FROM impacts
        WHERE avg_before IS NOT NULL AND avg_after IS NOT NULL
        GROUP BY impacts.symbol
        ORDER BY impacts.symbol
    """
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, {"period": pg_interval, "symbol": symbol})
            return cur.fetchall()


_INTERVAL_SECONDS = {"1m": 60, "5m": 300, "1h": 3600}


def get_price_history(symbol: str, from_ts: datetime, to_ts: datetime, interval: str):
    seconds = _INTERVAL_SECONDS.get(interval)
    if seconds is None:
        raise ValueError(f"unsupported interval '{interval}'; allowed: {list(_INTERVAL_SECONDS)}")
    if to_ts <= from_ts:
        raise ValueError("`to` must be after `from`")

    sql = """
        WITH bucketed AS (
            SELECT
                to_timestamp(floor(extract(epoch from trade_time) / %(sec)s) * %(sec)s)
                    AT TIME ZONE 'UTC' AS bucket_ts,
                price,
                size,
                trade_time
            FROM trades
            WHERE symbol = %(symbol)s
              AND trade_time >= %(from_ts)s
              AND trade_time <= %(to_ts)s
        ),
        ranked AS (
            SELECT
                bucket_ts, price, size,
                row_number() OVER (PARTITION BY bucket_ts ORDER BY trade_time ASC)  AS rn_asc,
                row_number() OVER (PARTITION BY bucket_ts ORDER BY trade_time DESC) AS rn_desc
            FROM bucketed
        )
        SELECT
            bucket_ts,
            max(CASE WHEN rn_asc  = 1 THEN price END) AS open,
            max(price)                                AS high,
            min(price)                                AS low,
            max(CASE WHEN rn_desc = 1 THEN price END) AS close,
            sum(size)                                 AS volume
        FROM ranked
        GROUP BY bucket_ts
        ORDER BY bucket_ts ASC
    """
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"sec": seconds, "symbol": symbol, "from_ts": from_ts, "to_ts": to_ts})
            return cur.fetchall()
