# 🤖 Crypto Futures Signal Bot — Setup Guide
### Powered by Gemini AI | Binance Futures

---

## 📁 Files List
```
trading_bot/
├── trading_bot.py      ← Main bot file
├── config.py           ← Apni settings yahan karo
├── requirements.txt    ← Dependencies
└── README.md           ← Ye file
```

---

## ⚙️ Step-by-Step Setup

### Step 1: Python Install Karo
Python 3.11+ install hona chahiye. Check karo:
```
python --version
```
Agar nahi hai: https://python.org se download karo

---

### Step 2: Dependencies Install Karo
Terminal/CMD kholo aur ye command run karo:
```
pip install -r requirements.txt
```

---

### Step 3: API Key Set Karo
`config.py` file kholo aur apni Gemini API key paste karo:
```python
GEMINI_API_KEY = "AIza...your_real_key_here..."
```

---

### Step 4: Symbols Customize Karo (Optional)
`config.py` mein jo symbols chahiye woh add/remove karo:
```python
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", ...]
```

---

### Step 5: Bot Run Karo
```
python trading_bot.py
```

---

## 📊 Signal Samajhna

| Signal | Matlab |
|--------|--------|
| 🟢 LONG  | Price badhne wali hai — Buy/Long position lo |
| 🔴 SHORT | Price girne wali hai — Sell/Short position lo |
| 🟡 WAIT  | Market unclear — Koi trade mat karo |

### Signal Details:
- **Entry Price** → Yahan pe position open karo
- **Stop Loss**   → Agar price yahan pahunche to exit karo (loss limit)
- **TP1/TP2/TP3** → Take profit levels (TP1 pe half close, TP2 pe quarter, TP3 pe rest)
- **Leverage**    → Bot suggest karta hai (3x, 5x, 10x)
- **Confidence**  → 7+/10 wale signals zyada reliable hain

---

## ⚙️ Configuration Options (config.py)

```python
TIMEFRAME = "15m"           # 1m, 5m, 15m, 1h, 4h
SCAN_INTERVAL_MINUTES = 5   # Har 5 min pe scan
MIN_CONFIDENCE = 6          # 6 se kam confidence pe WAIT
SYMBOLS = [...]             # Jo pairs chahiye
```

---

## 💾 Signal History
- Har signal `signals_history.csv` mein save hota hai
- Excel mein open kar ke apni performance track karo

---

## 🔄 24/7 Laptop Pe Run Karne Ke Liye
Laptop band na ho iske liye:
1. Windows: Power settings → "Never sleep"
2. Bot ko terminal mein run karo — Ctrl+C se band hoga

---

## ⚠️ IMPORTANT DISCLAIMERS

1. **Ye bot 100% accurate nahi hai** — koi bhi bot nahi hota
2. **Risk management zaroori hai** — kabhi bhi sara capital ek trade pe mat lagao
3. **Stop loss hamesha set karo** — bina SL ke trade mat karo
4. **Sirf wo paisa trade karo jo aap afford kar sako lose karna**
5. **Bot ke signals ko apni analysis se verify karo**

---

## 🛠️ Troubleshooting

**API Key Error:**
→ config.py mein sahi key paste karo

**Model Not Found Error:**
→ config.py mein GEMINI_MODEL name check karo
→ Google AI Studio pe available models dekho

**No Data Error:**
→ Internet connection check karo
→ Binance accessible hai ya nahi check karo

**Low Signals:**
→ MIN_CONFIDENCE ko 5 kar do config.py mein

---

## 📈 Best Practices

1. **15m timeframe** daytrading ke liye best hai
2. **3-5x leverage** se start karo, zyada leverage = zyada risk
3. **Always use Stop Loss** — ye bot wala SL use karo
4. **TP1 hit hone pe SL breakeven pe le aao**
5. **Market highly volatile ho to WAIT signal follow karo**

---

Good luck! 💰🚀
