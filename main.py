import requests
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from urllib.parse import quote
import streamlit as st
import time

nltk.download('vader_lexicon', quiet=True)

# ── CHANGE THIS ONE LINE ONLY ───────────────────────────────────────────
NEWS_API_KEY = "paste_your_newsapi_key_here"          # ← replace this!

THRESHOLD = 0.09   # suggest when edge ≥9%
MAX_MARKETS = 120  # check more markets

@st.cache_data(ttl=600)
def get_kalshi_markets():
  url = "https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=100"
  try:
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        return r.json().get('markets', [])
    except:
        return []

@st.cache_data(ttl=400)
def get_news(query):
    q = quote(query[:180])  # NewsAPI has query length limits
    url = f"https://newsapi.org/v2/everything?q={q}&sortBy=publishedAt&pageSize=15&apiKey={NEWS_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get('articles', [])
    except:
        return []

def sentiment_score(articles):
    sia = SentimentIntensityAnalyzer()
    scores = [sia.polarity_scores(' '.join(filter(None, [a.get(k) for k in ['title','description','content']])) )['compound']
              for a in articles if any(a.get(k) for k in ['title','description','content'])]
    return sum(scores)/len(scores) if scores else 0.0

def est_yes_prob(sent):
    return max(0.0, min(1.0, (sent + 1)/2 ))

# ── APP UI ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Kalshi News Edge Finder", layout="wide")
st.title("Kalshi Bet Suggestions — News Sentiment Scanner")
st.markdown(f"Flags bets with ≥{THRESHOLD*100:.0f}% edge vs current market price. Refreshes every 10 min. **Not advice — trade at own risk!**")

if st.button("🔄 Refresh Now", type="primary"):
    st.cache_data.clear()

with st.spinner("Scanning Kalshi markets + news..."):
    markets = get_kalshi_markets()
    if not markets:
        st.error("Couldn't reach Kalshi API right now. Try refresh.")
        st.stop()

    suggestions = []
    for m in markets:
        ticker = m['ticker']
        title  = m['title']
        yes_cents = m.get('yes_bid', 0) / 100   # using bid for conservative edge estimate
        if yes_cents <= 0.01 or yes_cents >= 0.99:
            continue

        query = title.replace("Will ","").replace("?","").replace(" happen","").strip()[:120]
        if len(query) < 8: continue

        arts = get_news(query)
        if len(arts) < 3: continue

        sent = sentiment_score(arts)
        est  = est_yes_prob(sent)

        edge_yes = est - yes_cents
        edge_no  = (1-est) - (1-yes_cents)

        if edge_yes > THRESHOLD:
            suggestions.append({
                'side': 'YES', 'ticker': ticker, 'title': title,
                'market_prob': yes_cents, 'est_prob': est, 'edge': edge_yes,
                'sentiment': sent
            })
        elif edge_no > THRESHOLD:
            suggestions.append({
                'side': 'NO', 'ticker': ticker, 'title': title,
                'market_prob': 1-yes_cents, 'est_prob': 1-est, 'edge': edge_no,
                'sentiment': sent
            })

if suggestions:
    st.success(f"Found {len(suggestions)} potential edges!")
    suggestions.sort(key=lambda x: x['edge'], reverse=True)
    for s in suggestions[:12]:   # show top 12
        emoji = "🟢" if s['edge'] > 0.12 else "🟡"
        st.markdown(f"**{emoji} Buy {s['side']}** — **{s['ticker']}**  \n{s['title']}")
        st.caption(f"Market ≈ {s['market_prob']:.0%}   |   News est. {s['est_prob']:.0%}   |   Edge **+{s['edge']:.0%}**   |   Sentiment {s['sentiment']:.2f}")
        st.markdown("---")
else:
    st.info("No clear edges right now (markets are pretty efficient). Check back later.")

st.caption(f"Last refresh: {time.strftime('%Y-%m-%d %H:%M UTC')}")
