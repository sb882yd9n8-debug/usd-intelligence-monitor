from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import calendar
import feedparser
import pandas as pd
import streamlit as st
import yfinance as yf
from engine import PAIRS, classify_news, technical, label, news_summary

st.set_page_config(page_title='USD Intelligence v2', page_icon='💵', layout='centered')
st.markdown('''<style>.block-container{padding-top:1rem;padding-left:1rem;padding-right:1rem}div[data-testid="stMetric"]{background:#192331;border-radius:12px;padding:12px}div[data-testid="stMetric"] *{color:#f4f6fa!important} </style>''', unsafe_allow_html=True)
st.title('💵 USD Intelligence Monitor 2.0')
st.caption('Semnale automate din piață și titluri de știri · nu reprezintă prognoză certificată')

@st.cache_data(ttl=900, show_spinner=False)
def prices(symbol, period, interval):
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty: return pd.Series(dtype=float)
    c = df['Close']
    if isinstance(c, pd.DataFrame): c = c.iloc[:,0]
    return pd.to_numeric(c, errors='coerce').dropna()

@st.cache_data(ttl=1800, show_spinner=False)
def news_feed(query):
    url = 'https://news.google.com/rss/search?q=' + quote(query + ' when:7d') + '&hl=en-US&gl=US&ceid=US:en'
    f = feedparser.parse(url)
    if getattr(f, 'bozo', False) and not f.entries: return [], 'RSS indisponibil'
    now = datetime.now(timezone.utc)
    out=[]
    for e in f.entries[:35]:
        t=e.get('published_parsed')
        if not t: continue
        when=datetime.fromtimestamp(calendar.timegm(t), timezone.utc)
        if not now-timedelta(days=7) <= when <= now+timedelta(minutes=10): continue
        direction, why = classify_news(e.get('title',''))
        out.append({'title':e.get('title',''), 'url':e.get('link',''), 'when':when, 'direction':direction, 'why':why, 'publisher':e.get('source',{}).get('title','') if isinstance(e.get('source'),dict) else ''})
    return out, None

with st.sidebar:
    st.header('Setări')
    timeframe = st.selectbox('Timeframe tehnic', ['1d','1h','15m'], index=0)
    period = {'1d':'2y','1h':'60d','15m':'60d'}[timeframe]
    st.caption('15m: Yahoo poate limita istoricul; EMA200 necesită 205 lumânări.')
    include_news = st.toggle('Include sentimentul automat al titlurilor', value=True)
    include_dxy = st.toggle('Include DXY în macro', value=True)
    include_spread = st.toggle('Include spread SUA–Germania 2Y (manual)', value=False)
    if include_spread:
        spread_now = st.number_input('Spread actual (puncte procentuale)', value=0.0, step=.01, format='%.2f')
        spread_ref = st.number_input('Spread de referință (puncte procentuale)', value=0.0, step=.01, format='%.2f')
        spread_date = st.date_input('Data verificării spreadului', value=datetime.now(timezone.utc).date())
    st.header('Prognoză publicată')
    st.caption('Se introduce numai o prognoză verificată, cu sursă și dată; nu este inventată de model.')
    forecast_direction = st.selectbox('Consens / prognoză verificată', ['Neintrodus','USD pozitiv','Neutru','USD negativ'])
    forecast_source = st.text_input('Sursă + dată (obligatoriu pentru includere)')
    include_forecast = forecast_direction != 'Neintrodus' and bool(forecast_source.strip())
    if forecast_direction != 'Neintrodus' and not include_forecast: st.warning('Completează sursa pentru a include prognoza.')
    if st.button('Actualizează datele'):
        prices.clear(); news_feed.clear(); st.rerun()

tech = {}
for pair,(ticker,orientation) in PAIRS.items():
    try: tech[pair] = technical(prices(ticker,period,timeframe), orientation)
    except Exception: tech[pair] = None
available=[v['vote'] for v in tech.values() if v is not None]
tech_score=sum(available) if available else None

macro=[]; details=[]
if include_dxy:
    try:
        dxy=prices('DX-Y.NYB','6mo','1d')
        if len(dxy)>=30:
            dxy_now=float(dxy.iloc[-1]); dxy_avg=float(dxy.ewm(span=20,adjust=False).mean().iloc[-1]); vote=1 if dxy_now>dxy_avg else -1 if dxy_now<dxy_avg else 0
            macro.append(vote); details.append(('DXY vs EMA20',vote,f'{dxy_now:.2f} vs {dxy_avg:.2f} · {str(dxy.index[-1])[:16]}'))
        else: details.append(('DXY',None,'Date insuficiente'))
    except Exception: details.append(('DXY',None,'Sursă indisponibilă'))
if include_spread:
    days_old=(datetime.now(timezone.utc).date()-spread_date).days
    if 0<=days_old<=7:
        vote=1 if spread_now>spread_ref else -1 if spread_now<spread_ref else 0
        macro.append(vote); details.append(('US–DE 2Y (manual)',vote,f'{spread_now:.2f} pp vs {spread_ref:.2f} pp · verificat {spread_date}'))
    else: details.append(('US–DE 2Y',None,'Data este în viitor sau mai veche de 7 zile: exclus'))

query='US dollar Federal Reserve forex EUR USD GBP JPY'
try: articles, feed_error=news_feed(query)
except Exception: articles, feed_error=[], 'RSS indisponibil'
news_result=news_summary(articles)
if include_news:
    if news_result is not None:
        macro.append(news_result['vote']); details.append(('Știri: titluri clasificate',news_result['vote'],f"{news_result['classified']} titluri · medie {news_result['average']:+.2f}"))
    else: details.append(('Știri',None,'Sub 3 titluri clasificate: exclus'))
if include_forecast:
    vote={'USD pozitiv':1,'Neutru':0,'USD negativ':-1}[forecast_direction]
    macro.append(vote); details.append(('Prognoză verificată (manual)',vote,forecast_source))
macro_score=sum(macro) if macro else None

st.subheader('Tablou de bord')
c1,c2=st.columns(2)
with c1: st.metric('MACRO · USD', label(macro_score) if macro_score is not None else 'FĂRĂ DATE', f'{macro_score:+d} / {len(macro)}' if macro_score is not None else 'N/A')
with c2: st.metric('TEHNIC · USD', label(tech_score) if tech_score is not None else 'FĂRĂ DATE', f'{tech_score:+d} / {len(available)}' if tech_score is not None else 'N/A')
if macro_score is None or tech_score is None: st.warning('Date insuficiente pentru o concluzie comună.')
elif macro_score>0 and tech_score>0: st.success('Confirmare: contextul macro și perechile valutare favorizează USD.')
elif macro_score<0 and tech_score<0: st.error('Confirmare: contextul macro și perechile valutare indică slăbiciune USD.')
else: st.info('Divergență / neutralitate: nu există confirmare comună.')

st.subheader('1 · Motor macro')
for name,vote,description in details:
    signal='🟢' if vote==1 else '🔴' if vote==-1 else '🟡' if vote==0 else '⚪'
    st.markdown(f'{signal} **{name}** — {description}')
st.caption('Scor de voturi, nu probabilitate și nu prognoză statistică. Titlurile nu sunt articolele integrale; clasificarea pe reguli poate greși negații, ironii sau contextul.')

st.subheader('2 · Motor tehnic')
rows=[]
for pair, v in tech.items():
    rows.append({'Pereche':pair, 'USD':label(v['vote']) if v else 'FĂRĂ DATE', 'Scor /4':f"{v['score']:+d}" if v else '—', 'RSI14':round(v['rsi'],1) if v else None, 'Ultima lumânare':v['timestamp'][:16] if v else '—'})
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
st.caption('Fiecare pereche votează −1, 0 sau +1; EMA20, EMA50, EMA200 și RSI14. EUR/USD și GBP/USD sunt inversate față de USD/JPY. Semnalele sunt calculate pe timeframe-ul selectat.')

st.subheader('3 · Știri USD: analiză explicabilă')
st.caption(f'{len(articles)} titluri din ultimele 7 zile · Google News RSS · actualizare cache 30 min · nu este flux profesional de știri')
if feed_error: st.warning(feed_error)
if not articles: st.warning('Nu sunt disponibile știri recente. Nu se generează concluzii din știri.')
for item in articles[:18]:
    symbol='🟢' if item['direction']==1 else '🔴' if item['direction']==-1 else '🟡' if item['direction']==0 else '⚪'
    st.markdown(f"{symbol} [{item['title']}]({item['url']})")
    st.caption(f"{item['when'].strftime('%Y-%m-%d %H:%M UTC')} · {item['why']}")

st.subheader('4 · Metodologie și limite')
with st.expander('Cum se formează scorurile?'):
    st.write('Macro: câte un vot pentru DXY vs EMA20, variația spreadului 2Y verificat manual, direcția clasificată a titlurilor și prognoza verificată manual. Sursele lipsă sunt excluse, nu tratate ca neutre.')
    st.write('Tehnic: 4 condiții per pereche (preț vs EMA20, EMA20 vs EMA50, preț vs EMA200, RSI14); scor ≥2 produce vot +1 USD, scor ≤−2 vot −1, altfel 0. Inversarea EUR/USD și GBP/USD este inclusă.')
    st.write('Sentimentul din titluri este euristic și poate reflecta mișcări deja produse. Nu este un consens al analiștilor, nu este o probabilitate și nu reprezintă un model AI care citește articolele integrale.')
st.caption('Yahoo Finance este sursă neoficială, posibil întârziată sau incompletă. Verifică prețurile și sursele înainte de decizii financiare.')
