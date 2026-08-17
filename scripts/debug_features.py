"""Debug script for feature engineering issue."""
import pandas as pd

df = pd.read_parquet("data/research/v1/BINANCE/BTC-USDT/1H/candles.parquet")
df = df.sort_values("timestamp").reset_index(drop=True)
close = df["close"]
high = df["high"]
low = df["low"]
volume = df["volume"]

print(f"Total rows: {len(df)}")

features = pd.DataFrame()
features["market_id"] = "BTC-USDT"
features["exchange_id"] = "BINANCE"
features["timestamp"] = df["timestamp"]

# Price returns
features["return_1h"] = close.pct_change(1)
features["return_4h"] = close.pct_change(4)
features["return_24h"] = close.pct_change(24)
features["return_7d"] = close.pct_change(168)

# Volatility
returns_1h = close.pct_change(1)
features["volatility_24h"] = returns_1h.rolling(24).std()
features["volatility_7d"] = returns_1h.rolling(168).std()
features["volatility_30d"] = returns_1h.rolling(720).std()

# ATR
tr = pd.concat(
    [
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ],
    axis=1,
).max(axis=1)
features["atr_14"] = tr.rolling(14).mean()
features["atr_pct"] = features["atr_14"] / close

# Price position
rolling_high = high.rolling(168).max()
rolling_low = low.rolling(168).min()
features["price_position_7d"] = (close - rolling_low) / (rolling_high - rolling_low + 1e-10)

# Volume
features["volume_ratio_24h"] = volume / volume.rolling(24).mean()
features["volume_ratio_7d"] = volume / volume.rolling(168).mean()

# RSI
delta = close.diff()
gain = delta.where(delta > 0, 0.0)
loss = (-delta).where(delta < 0, 0.0)
avg_gain = gain.rolling(window=14).mean()
avg_loss = loss.rolling(window=14).mean()
rs = avg_gain / (avg_loss + 1e-10)
features["rsi_14"] = 100 - (100 / (1 + rs))

# MACD
ema_12 = close.ewm(span=12, adjust=False).mean()
ema_26 = close.ewm(span=26, adjust=False).mean()
macd = ema_12 - ema_26
signal = macd.ewm(span=9, adjust=False).mean()
features["macd_signal"] = macd - signal

# Trend
sma_20 = close.rolling(20).mean()
sma_50 = close.rolling(50).mean()
features["trend_strength"] = (sma_20 - sma_50) / sma_50

# Range width
features["range_width_7d"] = (rolling_high - rolling_low) / close

print(f"Before dropna: {len(features)}")
print("Null counts per column:")
print(features.isnull().sum())
print()

features_clean = features.dropna()
print(f"After dropna: {len(features_clean)}")