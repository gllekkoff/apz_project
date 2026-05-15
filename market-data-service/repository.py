import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from cassandra.cluster import Cluster, Session
from cassandra.query import SimpleStatement
from fastapi import HTTPException

from models import MomentumRow, Trade, VolatilityAlertRow, WhaleAlertRow


def connect_cassandra() -> Session:
    hosts = [h.strip() for h in os.getenv("CASSANDRA_HOSTS", "cassandra").split(",") if h.strip()]
    keyspace = os.getenv("CASSANDRA_KEYSPACE", "crypto")
    last_exc: Optional[Exception] = None

    for _ in range(60):
        try:
            return Cluster(hosts, protocol_version=5).connect(keyspace)
        except Exception as exc:
            last_exc = exc
            time.sleep(3)

    raise RuntimeError(f"Cassandra not reachable at {hosts}: {last_exc}")


class MarketDataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def health(self) -> dict:
        try:
            row = self.session.execute("SELECT release_version FROM system.local").one()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"cassandra error: {exc}") from exc
        return {"status": "ok", "cassandra": row.release_version if row else "unknown"}

    def trades(
        self,
        symbol: str,
        min_size: Optional[float],
        side: Optional[str],
        limit: int,
        days: int,
    ) -> List[Trade]:
        now = datetime.now(timezone.utc)
        date_keys = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        over_fetch = limit * 10
        stmt = SimpleStatement(
            "SELECT symbol, trade_time, trade_id, price, size, side "
            "FROM trades WHERE symbol = %s AND date = %s LIMIT %s"
        )

        out: List[Trade] = []
        for date_key in date_keys:
            try:
                rows = self.session.execute(stmt, (symbol, date_key, over_fetch))
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"cassandra error: {exc}") from exc

            for row in rows:
                if min_size is not None and row.size < min_size:
                    continue
                if side is not None and row.side != side:
                    continue
                out.append(
                    Trade(
                        symbol=row.symbol,
                        trade_time=row.trade_time,
                        trade_id=row.trade_id,
                        price=row.price,
                        size=row.size,
                        side=row.side,
                    )
                )
                if len(out) >= limit:
                    return out
        return out

    def momentum(self, symbol: str, minutes: int) -> List[MomentumRow]:
        try:
            rows = self.session.execute(
                "SELECT symbol, minute_ts, current_price, price_change_pct, volume, buy_sell_ratio "
                "FROM market_momentum WHERE symbol = %s LIMIT %s",
                (symbol, minutes),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"cassandra error: {exc}") from exc

        return [
            MomentumRow(
                symbol=row.symbol,
                minute_ts=row.minute_ts,
                current_price=row.current_price,
                price_change_pct=row.price_change_pct,
                volume=row.volume,
                buy_sell_ratio=row.buy_sell_ratio,
            )
            for row in rows
        ]

    def whale_alerts(self, symbol: str, limit: int) -> List[WhaleAlertRow]:
        try:
            rows = self.session.execute(
                "SELECT symbol, alert_time, trade_size, threshold_95p, price, side, deviation_percent "
                "FROM whale_alerts WHERE symbol = %s LIMIT %s",
                (symbol, limit),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"cassandra error: {exc}") from exc

        return [
            WhaleAlertRow(
                symbol=row.symbol,
                alert_time=row.alert_time,
                trade_size=row.trade_size,
                threshold_95p=row.threshold_95p,
                price=row.price,
                side=row.side,
                deviation_percent=row.deviation_percent,
            )
            for row in rows
        ]

    def volatility_alerts(self, symbol: str, limit: int) -> List[VolatilityAlertRow]:
        try:
            rows = self.session.execute(
                "SELECT symbol, alert_time, current_volatility, previous_volatility, ratio "
                "FROM volatility_alerts WHERE symbol = %s LIMIT %s",
                (symbol, limit),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"cassandra error: {exc}") from exc

        return [
            VolatilityAlertRow(
                symbol=row.symbol,
                alert_time=row.alert_time,
                current_volatility=row.current_volatility,
                previous_volatility=row.previous_volatility,
                ratio=row.ratio,
            )
            for row in rows
        ]
