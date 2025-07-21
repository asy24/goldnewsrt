import os, pprint
pprint.pprint({
    'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
    'CHAT_ID': os.getenv('CHAT_ID'),
    'AV_API_KEY': os.getenv('AV_API_KEY'),
})

import os
import asyncio
import feedparser
import pandas as pd
from datetime import datetime, timezone
from telegram import Bot
from telegram.error import BadRequest
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID")       # should be the integer ID of your chat
AV_API_KEY     = os.getenv("AV_API_KEY")    # Alpha Vantage key

if not all([TELEGRAM_TOKEN, CHAT_ID, AV_API_KEY]):
    raise RuntimeError("Missing one of TELEGRAM_TOKEN, CHAT_ID, or AV_API_KEY in environment")

CHAT_ID = int(CHAT_ID)
bot = Bot(token=TELEGRAM_TOKEN)

# ─── RSI FUNCTION (pure pandas) ─────────────────────────────────────────────────
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ─── SENTIMENT ─────────────────────────────────────────────────────────────────
analyzer = SentimentIntensityAnalyzer()
def score_text(text: str):
    score = analyzer.polarity_scores(text[:200])["compound"]
    label = "POSITIVE" if score >= 0 else "NEGATIVE"
    return label, abs(score)

# ─── DATA FETCHERS ────────────────────────────────────────────────────────────────
def fetch_gdelt_events():
    url = "http://data.gdeltproject.org/api/v2/doc/doc?query=gold OR USD&mode=RSS"
    return feedparser.parse(url).entries[:5]

def fetch_ecb_rss():
    url = "https://www.ecb.europa.eu/rss/fxref-usd.html"
    return feedparser.parse(url).entries

def fetch_fx(symbol: str = "XAUUSD", interval: str = "15min") -> pd.DataFrame:
    url = (
        f"https://www.alphavantage.co/query?"
        f"function=FX_INTRADAY&from_symbol={symbol[:3]}&to_symbol={symbol[3:]}&"
        f"interval={interval}&apikey={AV_API_KEY}&datatype=csv"
    )
    df = pd.read_csv(url)
    df['timestamp'] = pd.to_datetime(df.timestamp)
    return df.sort_values("timestamp")

# ─── ALERT LOGIC & DISPATCH ───────────────────────────────────────────────────────
async def scan_and_dispatch():
    # GDELT
    for e in fetch_gdelt_events():
        label, score = score_text(e.title)
        if label == "NEGATIVE":
            await bot.send_message(chat_id=CHAT_ID, text=f"📰 [GDELT] {e.title} ({score:.2f})")
    # ECB
    for e in fetch_ecb_rss():
        if "interest rate" in e.title.lower():
            await bot.send_message(
                chat_id=CHAT_ID,
                text=f"🏦 [ECB] {e.title}\n📅 {e.published}"
            )
    # RSI
    df = fetch_fx()
    df.set_index("timestamp", inplace=True)
    df["RSI14"] = compute_rsi(df["close"], period=14)
    last_rsi = df["RSI14"].iloc[-1]
    if last_rsi < 30:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"📉 [TA] XAU/USD RSI14 oversold: {last_rsi:.1f}"
        )

async def main():
    try:
        # Test sending a startup ping
        bot.send_message(chat_id=CHAT_ID, text="🤖 Bot starting up...")
    except BadRequest as e:
        raise RuntimeError(f"Startup check failed: {e}")

    while True:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        await bot.send_message(chat_id=CHAT_ID, text=f"⏰ Scan at {now}")
        await scan_and_dispatch()
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
