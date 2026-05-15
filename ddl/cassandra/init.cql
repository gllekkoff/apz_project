CREATE KEYSPACE IF NOT EXISTS crypto
    WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 2}
    AND durable_writes = true;

ALTER KEYSPACE crypto
    WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 2}
    AND durable_writes = true;

USE crypto;

CREATE TABLE IF NOT EXISTS market_momentum (
    symbol             text,
    minute_ts          timestamp,
    current_price      double,
    price_change_pct   double,
    volume             double,
    buy_sell_ratio     double,
    PRIMARY KEY (symbol, minute_ts)
) WITH CLUSTERING ORDER BY (minute_ts DESC);

CREATE TABLE IF NOT EXISTS trades (
    symbol     text,
    date       text,
    trade_time timestamp,
    trade_id   text,
    price      double,
    size       double,
    side       text,
    PRIMARY KEY ((symbol, date), trade_time, trade_id)
) WITH CLUSTERING ORDER BY (trade_time DESC, trade_id ASC);

CREATE TABLE IF NOT EXISTS whale_alerts (
    symbol             text,
    alert_time         timestamp,
    trade_size         double,
    threshold_95p      double,
    price              double,
    side               text,
    deviation_percent  double,
    PRIMARY KEY (symbol, alert_time)
) WITH CLUSTERING ORDER BY (alert_time DESC);

CREATE TABLE IF NOT EXISTS volatility_alerts (
    symbol               text,
    alert_time           timestamp,
    current_volatility   double,
    previous_volatility  double,
    ratio                double,
    PRIMARY KEY (symbol, alert_time)
) WITH CLUSTERING ORDER BY (alert_time DESC);
