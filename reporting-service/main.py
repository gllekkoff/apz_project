from datetime import datetime
import os
from typing import List, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import repository

app = FastAPI(title="Reporting Service", version="0.1.0")


class HourlyReportRow(BaseModel):
    symbol: str
    hour_ts: datetime
    trade_count: int
    total_volume_usd: float
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    avg_price: Optional[float] = None
    price_std: Optional[float] = None
    buy_volume: Optional[float] = None
    sell_volume: Optional[float] = None
    dominant_side: Optional[str] = None


class TradingPatternRow(BaseModel):
    hour_of_day: int
    avg_trade_count: Optional[float] = None
    avg_volume_usd: Optional[float] = None
    avg_volatility: Optional[float] = None
    avg_spread: Optional[float] = None
    sample_hours: Optional[int] = None


class TradingPatternsResponse(BaseModel):
    symbol: str
    computed_at: Optional[datetime] = None
    patterns: List[TradingPatternRow]
    top_activity_hours: List[int]
    top_volatility_hours: List[int]


class WhaleImpactRow(BaseModel):
    symbol: str
    large_trade_count: int
    avg_large_trade_size: Optional[float] = None
    p90_threshold: Optional[float] = None
    avg_impact_pct: Optional[float] = None
    avg_buy_impact_pct: Optional[float] = None
    avg_sell_impact_pct: Optional[float] = None


class OHLCVBar(BaseModel):
    bucket_ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/reports/hourly", response_model=List[HourlyReportRow])
def hourly_report(symbol: str = Query(...), hours: int = Query(12, ge=1, le=168)) -> List[HourlyReportRow]:
    try:
        rows = repository.get_hourly_reports(symbol, hours)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail=f"postgres error: {exc}") from exc
    return [HourlyReportRow(**r) for r in rows]


@app.get("/analytics/trading-patterns", response_model=TradingPatternsResponse)
def trading_patterns(symbol: str = Query(...)) -> TradingPatternsResponse:
    try:
        rows = repository.get_trading_patterns(symbol)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail=f"postgres error: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"no trading patterns yet for {symbol}; run batch jobs or seed demo data")

    patterns = [TradingPatternRow(**{k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    top_activity = sorted(rows, key=lambda r: -(r.get("avg_trade_count") or 0))[:3]
    top_vol = sorted(rows, key=lambda r: -(r.get("avg_volatility") or 0))[:3]

    return TradingPatternsResponse(
        symbol=symbol,
        computed_at=rows[0].get("computed_at"),
        patterns=patterns,
        top_activity_hours=[r["hour_of_day"] for r in top_activity],
        top_volatility_hours=[r["hour_of_day"] for r in top_vol],
    )


@app.get("/analytics/whale-impact", response_model=List[WhaleImpactRow])
def whale_impact(symbol: Optional[str] = Query(None), period: str = Query("24h")) -> List[WhaleImpactRow]:
    try:
        rows = repository.get_whale_impact(symbol, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail=f"postgres error: {exc}") from exc
    return [WhaleImpactRow(**r) for r in rows]


@app.get("/price/{symbol}", response_model=List[OHLCVBar])
def price_history(symbol: str, from_: datetime = Query(..., alias="from"), to: datetime = Query(...), interval: str = Query("1m")) -> List[OHLCVBar]:
    try:
        rows = repository.get_price_history(symbol, from_, to, interval)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail=f"postgres error: {exc}") from exc

    return [OHLCVBar(bucket_ts=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in rows]


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("reporting-service.main:app", host="0.0.0.0", port=port, log_level="info")
