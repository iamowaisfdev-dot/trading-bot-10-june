"""
╔══════════════════════════════════════════════════════════════╗
║     CRYPTO FUTURES SIGNAL BOT — Powered by Gemini AI        ║
║     Market: Binance Futures | Built with Python              ║
╚══════════════════════════════════════════════════════════════╝
DISCLAIMER: Ye bot sirf educational/informational signals deta hai.
Trading mein risk hota hai. Apni responsibility par trade karo.
"""

import os, sys, json, time, warnings, requests, csv
import pandas as pd
import numpy as np
from datetime import datetime

warnings.filterwarnings("ignore")

from rich.console import Console
from rich.table   import Table
from rich.panel   import Panel
from rich.text    import Text
from rich.columns import Columns
from rich         import box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.align   import Align

import google.generativeai as genai
from config import (
    GEMINI_API_KEY, GEMINI_MODEL, SYMBOLS, TIMEFRAME,
    SCAN_INTERVAL_MINUTES, LOOKBACK_CANDLES,
    MIN_CONFIDENCE, RISK_PER_TRADE_PERCENT, SIGNAL_LOG_FILE
)

console = Console()

# ══════════════════════════════════════════════════════════════
#  HELPER: None-safe number formatting
# ══════════════════════════════════════════════════════════════

def fmt(value, decimals=6, fallback="N/A"):
    """None ya invalid value ko safely format karo"""
    try:
        if value is None:
            return fallback
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return fallback

def safe_float(value, default=0.0):
    """None/string ko safely float mein convert karo"""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# ══════════════════════════════════════════════════════════════
#  1. BINANCE DATA FETCHER
# ══════════════════════════════════════════════════════════════

def fetch_ohlcv(symbol, interval="15m", limit=150):
    url    = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        df  = pd.DataFrame(raw, columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_vol","trades",
            "taker_buy_base","taker_buy_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.dropna(subset=["open","high","low","close","volume"])
        return df[["timestamp","open","high","low","close","volume"]].copy()
    except Exception as e:
        console.print(f"[red]❌ Data fetch error ({symbol}): {e}[/red]")
        return None


def get_funding_rate(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        r   = requests.get(url, params={"symbol": symbol, "limit": 1}, timeout=10)
        data = r.json()
        return float(data[0]["fundingRate"]) * 100 if data else 0.0
    except:
        return 0.0


# ══════════════════════════════════════════════════════════════
#  2. TECHNICAL INDICATORS
# ══════════════════════════════════════════════════════════════

def calculate_indicators(df):
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["volume"]

    # RSI
    delta    = close.diff()
    avg_gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    rs        = avg_gain / (avg_loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema12          = close.ewm(span=12, adjust=False).mean()
    ema26          = close.ewm(span=26, adjust=False).mean()
    df["macd"]     = ema12 - ema26
    df["macd_sig"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]= df["macd"] - df["macd_sig"]

    # EMAs
    df["ema9"]   = close.ewm(span=9,   adjust=False).mean()
    df["ema21"]  = close.ewm(span=21,  adjust=False).mean()
    df["ema50"]  = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # Bollinger Bands
    df["bb_mid"]   = close.rolling(20).mean()
    bb_std         = close.rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / (df["bb_mid"] + 1e-10)

    # Stochastic
    low14         = low.rolling(14).min()
    high14        = high.rolling(14).max()
    df["stoch_k"] = 100 * (close - low14) / (high14 - low14 + 1e-10)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # ATR
    tr1       = high - low
    tr2       = (high - close.shift()).abs()
    tr3       = (low  - close.shift()).abs()
    tr        = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=14, adjust=False).mean()

    # Volume
    df["vol_ma20"]  = vol.rolling(20).mean()
    df["vol_ratio"] = vol / (df["vol_ma20"] + 1e-10)

    return df.dropna(subset=["rsi","macd","ema50","atr"])


def get_support_resistance(df):
    recent     = df.tail(50)
    resistance = recent["high"].rolling(20).max().iloc[-1]
    support    = recent["low"].rolling(20).min().iloc[-1]
    pivot      = (resistance + support + recent["close"].iloc[-1]) / 3
    return round(float(support), 6), round(float(resistance), 6), round(float(pivot), 6)


def detect_candlestick_pattern(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last["close"] - last["open"])
    rng  = last["high"] - last["low"] + 1e-10
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_wick = last["high"] - max(last["open"], last["close"])

    if body / rng < 0.1:
        return "DOJI (Indecision)"
    if lower_wick > 2 * body and upper_wick < body:
        return "HAMMER (Bullish)"
    if upper_wick > 2 * body and lower_wick < body:
        return "SHOOTING STAR (Bearish)"
    if (last["close"] > last["open"] and prev["close"] < prev["open"]
            and last["open"] < prev["close"] and last["close"] > prev["open"]):
        return "BULLISH ENGULFING"
    if (last["close"] < last["open"] and prev["close"] > prev["open"]
            and last["open"] > prev["close"] and last["close"] < prev["open"]):
        return "BEARISH ENGULFING"
    return "Normal Candle"


# ══════════════════════════════════════════════════════════════
#  3. GEMINI AI ANALYSIS
# ══════════════════════════════════════════════════════════════

def build_prompt(symbol, df):
    last    = df.iloc[-1]
    support, resistance, pivot = get_support_resistance(df)
    pattern = detect_candlestick_pattern(df)
    funding = get_funding_rate(symbol)

    trend = (
        "STRONG BULLISH" if last["ema9"] > last["ema21"] > last["ema50"] > last["ema200"]
        else "BULLISH"   if last["ema9"] > last["ema21"] > last["ema50"]
        else "STRONG BEARISH" if last["ema9"] < last["ema21"] < last["ema50"] < last["ema200"]
        else "BEARISH"   if last["ema9"] < last["ema21"] < last["ema50"]
        else "SIDEWAYS"
    )
    bb_pos = (
        "ABOVE UPPER BAND (Overbought)" if last["close"] > last["bb_upper"]
        else "BELOW LOWER BAND (Oversold)" if last["close"] < last["bb_lower"]
        else "INSIDE BANDS"
    )
    vol_status = (
        "HIGH VOLUME" if last["vol_ratio"] > 1.5
        else "LOW VOLUME"  if last["vol_ratio"] < 0.7
        else "NORMAL VOLUME"
    )

    return f"""You are a professional crypto futures trader. Analyze {symbol} and return ONLY a JSON object.

SYMBOL: {symbol} | TIMEFRAME: {TIMEFRAME} | PRICE: {float(last['close']):.6f} USDT
Funding Rate: {funding:.4f}% | Pattern: {pattern}

TREND: {trend}
EMA9={float(last['ema9']):.4f} EMA21={float(last['ema21']):.4f} EMA50={float(last['ema50']):.4f}

RSI={float(last['rsi']):.2f} | MACD_HIST={float(last['macd_hist']):.8f}
Stoch_K={float(last['stoch_k']):.2f} | Stoch_D={float(last['stoch_d']):.2f}

Bollinger: {bb_pos} | BB_WIDTH={float(last['bb_width']):.4f}
ATR={float(last['atr']):.6f} | Volume: {vol_status} ({float(last['vol_ratio']):.2f}x)

Support={support:.6f} | Pivot={pivot:.6f} | Resistance={resistance:.6f}

LAST 5 CANDLES:
{df[['timestamp','open','high','low','close','volume']].tail(5).to_string(index=False)}

Return ONLY this JSON (all numeric fields must be actual numbers, never null or string):
{{"signal":"LONG or SHORT or WAIT","confidence":7,"entry_price":105000.5,"stop_loss":104000.0,"take_profit_1":106000.0,"take_profit_2":107000.0,"take_profit_3":108000.0,"risk_reward":2.0,"suggested_leverage":5,"market_condition":"TRENDING","reasoning":"Brief reason here","key_risk":"Main risk here"}}

RULES:
- signal=LONG or SHORT only if confidence>={MIN_CONFIDENCE}, else WAIT
- stop_loss = entry +/- ATR*1.5
- TP1=1:1 RR, TP2=1:2, TP3=1:3
- leverage: 3=low, 5=medium, 10=high confidence
- ALL numeric values must be real numbers (no null, no N/A)
- JSON ONLY, zero extra text"""


def get_gemini_signal(symbol, df):
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model  = genai.GenerativeModel(GEMINI_MODEL)
        prompt = build_prompt(symbol, df)

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=500,
            )
        )

        text = response.text.strip()

        # Strip markdown fences if present
        for fence in ["```json", "```"]:
            if fence in text:
                text = text.split(fence)[-1].split("```")[0].strip()

        # Extract JSON object
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        result = json.loads(text)

        # ── Sanitize ALL numeric fields (prevent NoneType format errors) ──
        price_now = float(df["close"].iloc[-1])
        atr_now   = float(df["atr"].iloc[-1])

        result["signal"]            = str(result.get("signal", "WAIT")).upper()
        result["confidence"]        = safe_int(result.get("confidence"), 0)
        result["entry_price"]       = safe_float(result.get("entry_price"), price_now)
        result["stop_loss"]         = safe_float(result.get("stop_loss"),   price_now - atr_now * 1.5)
        result["take_profit_1"]     = safe_float(result.get("take_profit_1"), price_now + atr_now)
        result["take_profit_2"]     = safe_float(result.get("take_profit_2"), price_now + atr_now * 2)
        result["take_profit_3"]     = safe_float(result.get("take_profit_3"), price_now + atr_now * 3)
        result["risk_reward"]       = safe_float(result.get("risk_reward"),   2.0)
        result["suggested_leverage"]= safe_int(result.get("suggested_leverage"), 3)
        result["market_condition"]  = str(result.get("market_condition", "RANGING"))
        result["reasoning"]         = str(result.get("reasoning", "No reasoning provided"))
        result["key_risk"]          = str(result.get("key_risk", "Market volatility"))

        # Enforce confidence rule
        if result["confidence"] < MIN_CONFIDENCE:
            result["signal"] = "WAIT"

        return result

    except json.JSONDecodeError as e:
        console.print(f"[yellow]⚠️ JSON parse error ({symbol}): {e}[/yellow]")
        price_now = float(df["close"].iloc[-1])
        return {
            "signal": "WAIT", "confidence": 0,
            "entry_price": price_now, "stop_loss": 0.0,
            "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0,
            "risk_reward": 0.0, "suggested_leverage": 3,
            "market_condition": "UNKNOWN",
            "reasoning": "AI response parse error - skipping signal",
            "key_risk": "API response format issue"
        }
    except Exception as e:
        console.print(f"[red]❌ Gemini error ({symbol}): {e}[/red]")
        price_now = float(df["close"].iloc[-1]) if df is not None and len(df) > 0 else 0.0
        return {
            "signal": "ERROR", "confidence": 0,
            "entry_price": price_now, "stop_loss": 0.0,
            "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0,
            "risk_reward": 0.0, "suggested_leverage": 3,
            "market_condition": "UNKNOWN",
            "reasoning": f"Error: {str(e)}",
            "key_risk": "API connection issue"
        }


# ══════════════════════════════════════════════════════════════
#  4. SIGNAL LOGGER
# ══════════════════════════════════════════════════════════════

def log_signal(symbol, sig, price):
    fieldnames = [
        "timestamp","symbol","signal","confidence","entry_price",
        "stop_loss","take_profit_1","take_profit_2","take_profit_3",
        "leverage","market_condition","reasoning"
    ]
    file_exists = os.path.exists(SIGNAL_LOG_FILE)
    try:
        with open(SIGNAL_LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "timestamp"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol"          : symbol,
                "signal"          : sig.get("signal", "?"),
                "confidence"      : sig.get("confidence", 0),
                "entry_price"     : sig.get("entry_price", price),
                "stop_loss"       : sig.get("stop_loss", 0),
                "take_profit_1"   : sig.get("take_profit_1", 0),
                "take_profit_2"   : sig.get("take_profit_2", 0),
                "take_profit_3"   : sig.get("take_profit_3", 0),
                "leverage"        : sig.get("suggested_leverage", 0),
                "market_condition": sig.get("market_condition", ""),
                "reasoning"       : sig.get("reasoning", ""),
            })
    except Exception as e:
        console.print(f"[yellow]⚠️ Log error: {e}[/yellow]")


# ══════════════════════════════════════════════════════════════
#  5. TERMINAL DISPLAY
# ══════════════════════════════════════════════════════════════

def get_signal_style(signal):
    return {
        "LONG" : ("🟢 LONG",  "bold green",  "▲"),
        "SHORT": ("🔴 SHORT", "bold red",    "▼"),
        "WAIT" : ("🟡 WAIT",  "bold yellow", "◆"),
        "ERROR": ("❌ ERROR", "bold white",  "✗"),
    }.get(signal, ("⚪ ?", "white", "?"))


def confidence_bar(score):
    score = safe_int(score, 0)
    filled = "█" * score
    empty  = "░" * (10 - score)
    color  = "green" if score >= 7 else "yellow" if score >= 5 else "red"
    return f"[{color}]{filled}[/{color}]{empty} {score}/10"


def render_header():
    now = datetime.now().strftime("%A, %d %B %Y  |  %H:%M:%S")
    t   = Text()
    t.append("  ₿ ", style="bold yellow")
    t.append("CRYPTO FUTURES SIGNAL BOT", style="bold cyan")
    t.append("  •  Powered by Gemini AI  •  ", style="dim")
    t.append("Binance Futures\n", style="bold magenta")
    t.append(f"  📅 {now}", style="dim white")
    t.append(f"  |  Symbols: {len(SYMBOLS)}  |  TF: {TIMEFRAME}  |  Interval: {SCAN_INTERVAL_MINUTES}m", style="dim")
    return Panel(t, border_style="cyan", padding=(0,1))


def render_signal_panel(symbol, sig, price):
    signal         = sig.get("signal", "ERROR")
    label, style, arrow = get_signal_style(signal)
    conf           = safe_int(sig.get("confidence"), 0)
    entry          = safe_float(sig.get("entry_price"), price)
    sl             = safe_float(sig.get("stop_loss"),   0)
    tp1            = safe_float(sig.get("take_profit_1"), 0)
    tp2            = safe_float(sig.get("take_profit_2"), 0)
    tp3            = safe_float(sig.get("take_profit_3"), 0)
    rr             = safe_float(sig.get("risk_reward"),  0)
    lev            = safe_int(sig.get("suggested_leverage"), 3)

    if signal == "ERROR":
        return Panel(
            f"[red]{sig.get('reasoning', 'Unknown error')}[/red]",
            title=f"[bold]{symbol}[/bold]",
            border_style="red"
        )

    c = Text()
    c.append(f"\n  {arrow} Signal      : ", style="dim")
    c.append(f"{label}\n", style=style)
    c.append(f"  📊 Confidence  : ", style="dim")
    c.append(f"{confidence_bar(conf)}\n")
    c.append(f"  💵 Entry Price : ", style="dim")
    c.append(f"{entry:.6f}\n", style="bold white")
    c.append(f"  🛑 Stop Loss   : ", style="dim")
    c.append(f"{sl:.6f}\n", style="bold red")
    c.append(f"  🎯 TP1         : ", style="dim")
    c.append(f"{tp1:.6f}\n", style="green")
    c.append(f"  🎯 TP2         : ", style="dim")
    c.append(f"{tp2:.6f}\n", style="bright_green")
    c.append(f"  🎯 TP3         : ", style="dim")
    c.append(f"{tp3:.6f}\n", style="bold bright_green")
    c.append(f"  ⚡ Leverage    : ", style="dim")
    c.append(f"{lev}x\n", style="bold magenta")
    c.append(f"  📈 R/R Ratio   : ", style="dim")
    c.append(f"1:{rr:.1f}\n", style="cyan")
    c.append(f"  📌 Market      : ", style="dim")
    c.append(f"{sig.get('market_condition','?')}\n", style="yellow")
    c.append(f"\n  💡 ", style="dim")
    c.append(f"{sig.get('reasoning','')}\n", style="italic white")
    c.append(f"  ⚠️  Risk: ", style="dim")
    c.append(f"{sig.get('key_risk','')}\n", style="italic yellow")

    border = "green" if signal == "LONG" else "red" if signal == "SHORT" else "yellow"
    return Panel(c, title=f"[bold]{symbol}[/bold]  [dim]{price:.6f} USDT[/dim]",
                 border_style=border, padding=(0,1))


def render_summary_table(results):
    table = Table(
        title="📋 Signals Summary",
        box=box.ROUNDED, border_style="cyan",
        header_style="bold cyan", show_lines=True
    )
    table.add_column("Symbol",    style="bold white", justify="center")
    table.add_column("Signal",    justify="center",   min_width=10)
    table.add_column("Conf",      justify="center")
    table.add_column("Entry",     justify="right")
    table.add_column("Stop Loss", justify="right",    style="red")
    table.add_column("TP1",       justify="right",    style="green")
    table.add_column("Lev",       justify="center",   style="magenta")
    table.add_column("R/R",       justify="center",   style="cyan")
    table.add_column("Condition", justify="center",   style="yellow")

    for r in results:
        sig    = r["signal_data"]
        signal = sig.get("signal", "?")
        conf   = safe_int(sig.get("confidence"), 0)
        entry  = safe_float(sig.get("entry_price"), r["price"])
        sl     = safe_float(sig.get("stop_loss"), 0)
        tp1    = safe_float(sig.get("take_profit_1"), 0)
        rr     = safe_float(sig.get("risk_reward"), 0)
        lev    = safe_int(sig.get("suggested_leverage"), 3)

        sig_text = Text()
        if signal == "LONG":
            sig_text.append("🟢 LONG",  style="bold green")
        elif signal == "SHORT":
            sig_text.append("🔴 SHORT", style="bold red")
        elif signal == "WAIT":
            sig_text.append("🟡 WAIT",  style="bold yellow")
        else:
            sig_text.append("❌ ERR",   style="bold white")

        cc = "green" if conf >= 7 else "yellow" if conf >= 5 else "red"
        table.add_row(
            r["symbol"], sig_text,
            f"[{cc}]{conf}/10[/{cc}]",
            f"{entry:.4f}", f"{sl:.4f}", f"{tp1:.4f}",
            f"{lev}x", f"1:{rr:.1f}",
            sig.get("market_condition", "?"),
        )
    return table


def render_action_signals(results):
    actionable = [r for r in results if r["signal_data"].get("signal") in ("LONG","SHORT")]
    if not actionable:
        return Panel(
            "[yellow]No high-confidence signals right now. Market mein wait karo. 🧘[/yellow]",
            title="🎯 Action Signals", border_style="yellow"
        )
    c = Text()
    for r in actionable:
        sig    = r["signal_data"]
        signal = sig.get("signal")
        style  = "bold green" if signal == "LONG" else "bold red"
        entry  = safe_float(sig.get("entry_price"), r["price"])
        sl     = safe_float(sig.get("stop_loss"), 0)
        tp1    = safe_float(sig.get("take_profit_1"), 0)
        lev    = safe_int(sig.get("suggested_leverage"), 3)
        conf   = safe_int(sig.get("confidence"), 0)
        c.append(f"\n  {'▲' if signal=='LONG' else '▼'} {r['symbol']:12}", style=style)
        c.append(f"  Entry: {entry:.6f}  ", style="white")
        c.append(f"SL: {sl:.6f}  ", style="red")
        c.append(f"TP1: {tp1:.6f}  ", style="green")
        c.append(f"[{lev}x]  ", style="magenta")
        c.append(f"Conf: {conf}/10\n", style="cyan")
    return Panel(c, title="🎯 Action Signals (Trade These!)", border_style="bright_green")


# ── NTFY NOTIFICATION ─────────────────────────────────────────
NTFY_TOPIC = "my-personal-trading-bot"

def send_notification(symbol, sig):
    signal = sig.get("signal", "")
    if signal not in ("LONG", "SHORT"):
        return

    emoji   = "🟢" if signal == "LONG" else "🔴"
    entry   = safe_float(sig.get("entry_price"), 0)
    sl      = safe_float(sig.get("stop_loss"), 0)
    tp1     = safe_float(sig.get("take_profit_1"), 0)
    tp2     = safe_float(sig.get("take_profit_2"), 0)
    tp3     = safe_float(sig.get("take_profit_3"), 0)
    conf    = safe_int(sig.get("confidence"), 0)
    lev     = safe_int(sig.get("suggested_leverage"), 3)
    rr      = safe_float(sig.get("risk_reward"), 0)

    title   = f"{emoji} {signal} {symbol} | Conf: {conf}/10 | {lev}x Lev"
    message = (
        f"📌 Signal  : {signal}\n"
        f"💵 Entry   : {entry:.6f}\n"
        f"🛑 SL      : {sl:.6f}\n"
        f"🎯 TP1     : {tp1:.6f}\n"
        f"🎯 TP2     : {tp2:.6f}\n"
        f"🎯 TP3     : {tp3:.6f}\n"
        f"⚡ Leverage: {lev}x | R/R: 1:{rr:.1f}\n"
        f"💡 {sig.get('reasoning','')[:100]}"
    )

    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title"   : title.encode("utf-8"),        # ← encode fix
                "Priority": "high",
                "Tags"    : "white_check_mark" if signal == "LONG" else "rotating_light",
            },
            timeout=10
        )
        # Response check karo
        if resp.status_code == 200:
            console.print(f"[green]📲 Notification sent → {symbol} {signal} ✅[/green]")
        else:
            console.print(f"[red]❌ ntfy failed ({resp.status_code}): {resp.text}[/red]")
    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ ntfy: Internet connection error[/red]")
    except requests.exceptions.Timeout:
        console.print(f"[red]❌ ntfy: Request timeout[/red]")
    except Exception as e:
        console.print(f"[yellow]⚠️ Notification error ({symbol}): {type(e).__name__}: {e}[/yellow]")

# ══════════════════════════════════════════════════════════════
#  6. MAIN SCAN LOOP
# ══════════════════════════════════════════════════════════════

def run_scan():
    console.print(render_header())
    console.print()
    results   = []
    scan_time = datetime.now().strftime("%H:%M:%S")

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}[/cyan]"),
        console=console, transient=True
    ) as progress:
        task = progress.add_task("Starting...", total=len(SYMBOLS))

        for symbol in SYMBOLS:
            progress.update(task, description=f"📥 Fetching  [bold]{symbol}[/bold]...")
            df = fetch_ohlcv(symbol, TIMEFRAME, LOOKBACK_CANDLES)

            if df is None or len(df) < 50:
                results.append({
                    "symbol": symbol, "price": 0.0,
                    "signal_data": {
                        "signal": "ERROR", "confidence": 0,
                        "reasoning": "Data unavailable",
                        "entry_price": 0, "stop_loss": 0,
                        "take_profit_1": 0, "take_profit_2": 0, "take_profit_3": 0,
                        "risk_reward": 0, "suggested_leverage": 3,
                        "market_condition": "UNKNOWN", "key_risk": "No data"
                    }
                })
                progress.advance(task)
                continue

            df    = calculate_indicators(df)
            price = float(df["close"].iloc[-1])

            progress.update(task, description=f"🤖 AI Analyzing [bold]{symbol}[/bold]...")
            signal_data = get_gemini_signal(symbol, df)

            results.append({"symbol": symbol, "price": price, "signal_data": signal_data})

            if signal_data.get("signal") not in ("ERROR", None):
                log_signal(symbol, signal_data, price)
                send_notification(symbol, signal_data)
            progress.advance(task)
            time.sleep(1.5)  # Rate limit buffer

    console.print(f"[dim]🕐 Scan completed at {scan_time}[/dim]\n")
    console.print(render_summary_table(results))
    console.print()
    console.print(render_action_signals(results))
    console.print()

    # Detailed panels for LONG/SHORT only
    action = [r for r in results if r["signal_data"].get("signal") in ("LONG","SHORT")]
    if action:
        console.print("[bold cyan]📊 Detailed Signal Panels:[/bold cyan]")
        cols = [render_signal_panel(r["symbol"], r["signal_data"], r["price"]) for r in action]
        if len(cols) >= 2:
            console.print(Columns(cols, equal=True))
        else:
            for c in cols:
                console.print(c)

    return results


def countdown_display(minutes):
    total = minutes * 60
    for remaining in range(total, 0, -1):
        m = remaining // 60
        s = remaining % 60
        done  = 20 - int(remaining / total * 20)
        bar   = "█" * done + "░" * (20 - done)
        print(f"\r  ⏳ Next scan in: [{bar}] {m:02d}:{s:02d}    ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 60 + "\r", end="")


# ══════════════════════════════════════════════════════════════
#  7. ENTRY POINT
# ══════════════════════════════════════════════════════════════

def main():
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]₿  CRYPTO FUTURES SIGNAL BOT  ₿[/bold cyan]\n"
        "[dim]Powered by Gemini AI  •  Binance Futures Data[/dim]\n"
        "[yellow]⚠️  DISCLAIMER: Educational only. Trade at your own risk.[/yellow]",
        border_style="cyan", padding=(1,4)
    ))
    console.print()

    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        console.print("[bold red]❌ ERROR: config.py mein apni GEMINI_API_KEY set karo![/bold red]")
        sys.exit(1)

    console.print(f"[green]✅ Gemini API   : {GEMINI_MODEL}[/green]")
    console.print(f"[green]✅ Symbols      : {', '.join(SYMBOLS)}[/green]")
    console.print(f"[green]✅ Timeframe    : {TIMEFRAME}  |  Scan every: {SCAN_INTERVAL_MINUTES} mins[/green]")
    console.print(f"[green]✅ Min Conf     : {MIN_CONFIDENCE}/10[/green]")
    console.print(f"[green]✅ Log file     : {SIGNAL_LOG_FILE}[/green]")
    console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

    scan_count = 0
    while True:
        try:
            scan_count += 1
            import pytz
            pkt         = pytz.timezone("Asia/Karachi")
            now_pkt     = datetime.now(pkt)
            current_hour = now_pkt.hour

            if 10 <= current_hour < 24:
                console.rule(f"[cyan]🔍 Scan #{scan_count}  |  {now_pkt.strftime('%I:%M %p')} PKT[/cyan]")
                run_scan()
                console.print(f"[dim]💾 Saved to {SIGNAL_LOG_FILE} | Next scan in {SCAN_INTERVAL_MINUTES} mins[/dim]\n")
            else:
                console.print(f"[dim]💤 Market hours nahi hain ({now_pkt.strftime('%I:%M %p')} PKT) — next check in 2 hours...[/dim]\n")

            countdown_display(SCAN_INTERVAL_MINUTES)

        except KeyboardInterrupt:
            console.print("\n\n[yellow]⏹️  Bot stopped. Happy Trading! 💰[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]❌ Unexpected error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            console.print("[yellow]Retrying in 60 seconds...[/yellow]")
            time.sleep(60)



if __name__ == "__main__":
    main()
