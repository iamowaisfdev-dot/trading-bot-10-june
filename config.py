# ============================================================
#  TRADING BOT CONFIGURATION — Apni settings yahan set karo
# ============================================================

# 🔑 GEMINI API KEY — Apni real key yahan paste karo
GEMINI_API_KEY = "AQ.Ab8RN6I9E6QBFu5UImim8yXfEuWlyzDIaCNZD4nKF0BV8a_mWw"

# 🤖 Gemini Model
GEMINI_MODEL = "gemini-2.5-flash-lite"

# 📊 Jinhe scan karna chahte ho (Binance Futures symbols)
SYMBOLS = [
    "BTCUSDT",
    "BNBUSDT",
]

# ⏱️ Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h)
TIMEFRAME = "1h"

# 🔄 Har kitne minutes baad scan kare (default: 5)
SCAN_INTERVAL_MINUTES = 60

# 📉 Kitne candles ka data use karo analysis ke liye
LOOKBACK_CANDLES = 200

# ⚠️ Minimum confidence score jis par signal show karo (1-10)
MIN_CONFIDENCE = 7

# 🎯 Risk per trade % (capital ka kitna % risk karo)
RISK_PER_TRADE_PERCENT = 2.0

# 📁 Signal history file
SIGNAL_LOG_FILE = "signals_history.csv"
