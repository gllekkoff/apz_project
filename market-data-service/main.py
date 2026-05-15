from typing import List, Optional

from fastapi import FastAPI, Query

from models import MomentumRow, Trade, VolatilityAlertRow, WhaleAlertRow
from repository import MarketDataRepository, connect_cassandra


app = FastAPI(
    title="Market Data Service",
    description="Cassandra-backed real-time market data API.",
    version="1.0.0",
)

repo = MarketDataRepository(connect_cassandra())


@app.get("/health")
def health() -> dict:
    return repo.health()


def _add_get(paths: List[str], **kwargs):
    def decorator(func):
        for path in paths:
            app.get(path, **kwargs)(func)
        return func

    return decorator


@_add_get(
    ["/market/trades", "/market/api/trades", "/api/trades"],
    response_model=List[Trade],
    summary="Trade lookup with optional filters",
)
def trade_lookup(
    symbol: str = Query(..., description="Trading pair, e.g. XBTUSD"),
    min_size: Optional[float] = Query(None, ge=0, description="Minimum trade size in USD"),
    side: Optional[str] = Query(None, pattern="^(Buy|Sell)$", description="Trade side filter"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    days: int = Query(2, ge=1, le=7, description="How many recent UTC days to scan"),
) -> List[Trade]:
    return repo.trades(symbol=symbol, min_size=min_size, side=side, limit=limit, days=days)


@_add_get(
    ["/market/momentum/{symbol}", "/market/api/momentum/{symbol}", "/api/momentum/{symbol}"],
    response_model=List[MomentumRow],
    summary="Recent per-minute market momentum",
)
def get_momentum(symbol: str, minutes: int = Query(60, ge=1, le=1440)) -> List[MomentumRow]:
    return repo.momentum(symbol=symbol, minutes=minutes)


@_add_get(
    ["/market/alerts/whale/{symbol}", "/market/api/alerts/whale/{symbol}", "/api/alerts/whale/{symbol}"],
    response_model=List[WhaleAlertRow],
    summary="Recent whale alerts",
)
def get_whale_alerts(symbol: str, limit: int = Query(50, ge=1, le=500)) -> List[WhaleAlertRow]:
    return repo.whale_alerts(symbol=symbol, limit=limit)


@_add_get(
    ["/market/alerts/volatility/{symbol}", "/market/api/alerts/volatility/{symbol}", "/api/alerts/volatility/{symbol}"],
    response_model=List[VolatilityAlertRow],
    summary="Recent volatility alerts",
)
def get_volatility_alerts(symbol: str, limit: int = Query(50, ge=1, le=500)) -> List[VolatilityAlertRow]:
    return repo.volatility_alerts(symbol=symbol, limit=limit)
