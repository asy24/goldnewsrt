import asyncio
import feedparser
import pandas as pd
from datetime import datetime
from transformers import pipeline
from telegram import Bot
from ta.momentum import RSIIndicator

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8165619808:AAHOo8oYLLncW0VgCyZrdsytHnJtgvXSCbs"
CHAT_ID        = 123456789  # replace with your chat_id
AV_API_KEY     = "YOUR_ALPHA_VANTAGE_KEY"

bot = Bot(token=TELEGRAM_TOKEN)

# ─── 1) GDELT RSS ────────────────────────────────────────────────────────────────
def fetch_gdelt_events():
    url = "http://data.gdeltproject.org/api/v2/doc/doc?query=gold OR USD&mode=RSS"
    return feedparser.parse(url).entries[:5]

# ─── 2) ECB RSS ─────────────────────────────────────────────────────────────────
def fetch_ecb_rss():
    url = "https://www.ecb.europa.eu/rss/fxref-usd.html"
    return feedparser.parse(url).entries

# ─── 3) INTRADAY FX ──────────────────────────────────────────────────────────────
def fetch_fx(symbol="XAUUSD", interval="15min"):
    url = (
        f"https://www.alphavantage.co/query?"
        f"function=FX_INTRADAY&from_symbol={symbol[:3]}&to_symbol={symbol[3:]}&"
        f"interval={interval}&apikey={AV_API_KEY}&datatype=csv"
    )
    df = pd.read_csv(url)
    df['timestamp'] = pd.to_datetime(df.timestamp)
    return df.sort_values("timestamp")

# ─── 4) SENTIMENT ────────────────────────────────────────────────────────────────
sentiment = pipeline("sentiment-analysis")
def score_text(text: str):
    res = sentiment(text[:512])[0]
    return res['label'], res['score']

# ─── 5) ALERT LOGIC & DISPATCH ───────────────────────────────────────────────────
async def scan_and_dispatch():
    # 5a) GDELT events
    for e in fetch_gdelt_events():
        label, score = score_text(e.title)
        if label == "NEGATIVE":
            msg = f"📰 [GDELT] {e.title} ({score:.2f})"
            await bot.send_message(chat_id=CHAT_ID, text=msg)

    # 5b) ECB policy RSS
    for e in fetch_ecb_rss():
        if "interest rate" in e.title.lower():
            msg = f"🏦 [ECB] {e.title}\n📅 {e.published}"
            await bot.send_message(chat_id=CHAT_ID, text=msg)

    # 5c) Technical RSI on XAU/USD
    df = fetch_fx()
    df.set_index("timestamp", inplace=True)
    # compute RSI(14) via `ta`
    rsi_series = RSIIndicator(df['close'], window=14).rsi()
    last_rsi = rsi_series.iloc[-1]
    if last_rsi < 30:
        msg = f"📉 [TA] XAU/USD RSI14 oversold: {last_rsi:.1f}"
        await bot.send_message(chat_id=CHAT_ID, text=msg)

# ─── 6) MAIN LOOP ────────────────────────────────────────────────────────────────
async def main():
    while True:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await bot.send_message(chat_id=CHAT_ID, text=f"⏰ Scan at {now}")
        await scan_and_dispatch()
        await asyncio.sleep(300)  # wait 5 minutes

if __name__ == "__main__":
    asyncio.run(main())
