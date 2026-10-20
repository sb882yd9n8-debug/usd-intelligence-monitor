"""USD Intelligence Monitor 2.0: technical and headline classification engine."""
import re
import pandas as pd

PAIRS = {
    'EUR/USD': ('EURUSD=X', -1),
    'GBP/USD': ('GBPUSD=X', -1),
    'USD/JPY': ('JPY=X', 1),
}


def label(vote):
    if vote is None:
        return 'FĂRĂ DATE'
    return 'USD PUTERNIC' if vote > 0 else 'USD SLAB' if vote < 0 else 'NEUTRU'


def technical(close, orientation):
    """Four votes in pair direction, converted into USD direction."""
    if close is None:
        return None
    s = pd.to_numeric(pd.Series(close), errors='coerce').dropna().astype(float)
    if len(s) < 205 or orientation not in (-1, 1):
        return None
    ema20 = s.ewm(span=20, adjust=False).mean()
    ema50 = s.ewm(span=50, adjust=False).mean()
    ema200 = s.ewm(span=200, adjust=False).mean()
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    g, l = float(gain.iloc[-1]), float(loss.iloc[-1])
    rsi = 100.0 if l == 0 and g > 0 else 50.0 if l == 0 and g == 0 else 100 - 100/(1 + g/l)
    def sign(a, b):
        return int(a > b) - int(a < b)
    score_pair = sum((
        sign(s.iloc[-1], ema20.iloc[-1]),
        sign(ema20.iloc[-1], ema50.iloc[-1]),
        sign(s.iloc[-1], ema200.iloc[-1]),
        sign(rsi, 50),
    ))
    score = int(score_pair * orientation)
    vote = 1 if score >= 2 else -1 if score <= -2 else 0
    stamp = s.index[-1]
    return {'vote': vote, 'score': score, 'rsi': float(rsi), 'timestamp': str(stamp)}


# Headline-only, rule-based sentiment. Deliberately conservative.
_POSITIVE = (
    r'\bdollar (?:rises?|gains?|surges?|strengthens?|rebounds?|climbs?)\b',
    r'\busd (?:rises?|gains?|surges?|strengthens?|rebounds?|climbs?)\b',
    r'\b(?:hawkish fed|fed turns hawkish|higher for longer)\b',
    r'\b(?:rate hike|rate hikes|rates? (?:rise|rises|higher))\b',
    r'\b(?:eur/usd|eurusd|gbp/usd|gbpusd) (?:falls?|drops?|slides?|declines?)\b',
    r'\busd/jpy (?:rises?|gains?|climbs?)\b',
)
_NEGATIVE = (
    r'\bdollar (?:falls?|drops?|slides?|weakens?|declines?|slumps?)\b',
    r'\busd (?:falls?|drops?|slides?|weakens?|declines?|slumps?)\b',
    r'\b(?:dovish fed|fed turns dovish)\b',
    r'\b(?:rate cut|rate cuts|rates? (?:fall|falls|lower))\b',
    r'\b(?:eur/usd|eurusd|gbp/usd|gbpusd) (?:rises?|gains?|climbs?)\b',
    r'\busd/jpy (?:falls?|drops?|slides?|declines?)\b',
)


def classify_news(title):
    """Returns USD direction and a short explanation; ambiguous headlines abstain."""
    t = str(title).lower().replace('’', "'")
    positive = [p for p in _POSITIVE if re.search(p, t)]
    negative = [p for p in _NEGATIVE if re.search(p, t)]
    if re.search(r"\b(?:not|no|unlikely|denies|without)\b", t):
        return None, 'Negație/context ambiguu: neclasificat'
    if positive and negative:
        return None, 'Semnale contradictorii în titlu'
    if positive:
        return 1, 'Regulă textuală: favorabil USD'
    if negative:
        return -1, 'Regulă textuală: nefavorabil USD'
    return None, 'Fără semnal USD suficient de clar'


def news_summary(articles):
    """Require >=3 directional headlines; return equal-weight directional vote."""
    directions = [a.get('direction') for a in articles if a.get('direction') in (-1, 1)]
    if len(directions) < 3:
        return None
    average = sum(directions) / len(directions)
    vote = 1 if average > 0.2 else -1 if average < -0.2 else 0
    return {'vote': vote, 'classified': len(directions), 'average': average}