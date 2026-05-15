from datetime import datetime

from pydantic import BaseModel


class Trade(BaseModel):
    symbol: str
    trade_time: datetime
    trade_id: str
    price: float
    size: float
    side: str


class MomentumRow(BaseModel):
    symbol: str
    minute_ts: datetime
    current_price: float
    price_change_pct: float
    volume: float
    buy_sell_ratio: float


class WhaleAlertRow(BaseModel):
    symbol: str
    alert_time: datetime
    trade_size: float
    threshold_95p: float
    price: float
    side: str
    deviation_percent: float


class VolatilityAlertRow(BaseModel):
    symbol: str
    alert_time: datetime
    current_volatility: float
    previous_volatility: float
    ratio: float
