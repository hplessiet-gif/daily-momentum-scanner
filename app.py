import datetime as dt
import html
import re
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Daily Momentum • US', page_icon='📈', layout='wide')
st.title('📈 Daily Momentum — Scanner US')
st.caption('Source alternative : screener public TradingView (non officiel) • Données potentiellement différées • Sans compte pour les visiteurs')
st.warning('Le screener public peut être limité ou bloqué. RVOL = volume du jour / volume quotidien moyen (non ajusté à l’heure). Float et négociabilité BoursoBank non vérifiés.')

with st.sidebar:
    st.header('Filtres')
    gain_min = st.slider('Hausse minimum (%)', 0, 50, 10)
    price_min, price_max = st.slider('Prix ($)', 0.5, 50.0, (2.0, 20.0), 0.5)
    rvol_min = st.slider('RVOL quotidien minimum (approx.)', 1.0, 15.0, 5.0, 0.5)
    float_max = st.number_input('Float maximum souhaité (millions)', 1, 100, 10)
    strict = st.checkbox('Exiger RVOL connu', True)
    limit = st.slider('Nombre de candidats à examiner', 20, 200, 100, 20)
    st.caption('Le filtre float ne peut pas être appliqué sans source fiable. Les résultats indiquent N/D.')

TV_URL = 'https://scanner.tradingview.com/america/scan'
FIELDS = ['name', 'description', 'close', 'change', 'volume', 'average_volume_30d_calc', 'relative_volume_10d_calc', 'exchange']

@st.cache_data(ttl=300, show_spinner=False)
def scan_tv(gain, low, high, limit):
    payload = {
        'filter': [
            {'left':'type', 'operation':'equal', 'right':'stock'},
            {'left':'subtype', 'operation':'equal', 'right':'common'},
            {'left':'close', 'operation':'in_range', 'right':[low,high]},
            {'left':'change', 'operation':'greater', 'right':gain},
            {'left':'volume', 'operation':'greater', 'right':10000},
        ],
        'options': {'lang':'en'},
        'symbols': {'query': {'types': []}, 'tickers': []},
        'columns': FIELDS,
        'sort': {'sortBy':'change', 'sortOrder':'desc'},
        'range': [0, limit-1],
    }
    res = requests.post(TV_URL, json=payload, timeout=25, headers={
        'User-Agent':'Mozilla/5.0 (compatible; DailyMomentumScanner/1.0)',
        'Accept':'application/json', 'Content-Type':'application/json',
    })
    res.raise_for_status()
    result = res.json()
    if 'data' not in result:
        raise ValueError('Réponse du screener sans données exploitables')
    rows = []
    for item in result['data']:
        d = dict(zip(FIELDS, item.get('d', [])))
        symbol = str(d.get('name') or '').strip()
        if not symbol:
            continue
        vol, avg = d.get('volume'), d.get('average_volume_30d_calc')
        rvol = vol / avg if isinstance(vol,(int,float)) and isinstance(avg,(int,float)) and avg > 0 else None
        rows.append({
            'ticker': symbol, 'name': d.get('description') or symbol,
            'exchange': d.get('exchange') or '', 'price': d.get('close'),
            'change': d.get('change'), 'vol': vol, 'rvol': rvol,
            'tv_relative_volume': d.get('relative_volume_10d_calc'),
            'float': None,
        })
    return rows

@st.cache_data(ttl=900, show_spinner=False)
def get_news(ticker):
    url = 'https://news.google.com/rss/search?' + urlencode({
        'q': f'"{ticker}" stock when:3d', 'hl':'en-US', 'gl':'US', 'ceid':'US:en'
    })
    try:
        response = requests.get(url, timeout=12, headers={'User-Agent':'Mozilla/5.0'})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news = []
        for item in root.findall('./channel/item')[:5]:
            title = html.unescape(item.findtext('title') or '')
            link = item.findtext('link') or ''
            date = item.findtext('pubDate') or ''
            if title:
                news.append({'title':title, 'link':link, 'date':date})
        return news
    except (requests.RequestException, ET.ParseError):
        return []

if 'results' not in st.session_state:
    st.session_state.results = []

if st.button('🔎 Lancer le scan réel', type='primary'):
    with st.spinner('Recherche des actions américaines…'):
        try:
            candidates = scan_tv(gain_min, price_min, price_max, limit)
            st.session_state.results = [r for r in candidates if (r['rvol'] is not None and r['rvol'] >= rvol_min) or (r['rvol'] is None and not strict)]
            st.session_state.scanned_at = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            st.session_state.scan_error = None
        except (requests.RequestException, ValueError, KeyError) as exc:
            st.session_state.results = []
            st.session_state.scan_error = str(exc)

if st.session_state.get('scan_error'):
    st.error('Source TradingView inaccessible : ' + st.session_state.scan_error)
    st.info('La source publique est non officielle et peut bloquer les serveurs Streamlit. Aucun résultat fictif ne sera affiché.')

rows = st.session_state.results
if rows:
    st.success(f'{len(rows)} candidats • Scan : {st.session_state.get("scanned_at", "—")}')
    st.info('Le float inférieur à ' + str(float_max) + ' M est un objectif, PAS un critère validé : float indisponible. Les nouvelles ci-dessous ne prouvent pas le catalyseur de la hausse.')
    for r in rows:
        change = r['change']
        change_text = f'{change:+.1f}%' if isinstance(change,(int,float)) else 'N/D'
        with st.expander(f'{r["ticker"]} • {r["name"]} • {change_text}', expanded=False):
            a,b,c,d = st.columns(4)
            a.metric('Cours', f'${r["price"]:.2f}' if isinstance(r['price'],(int,float)) else 'N/D')
            b.metric('Hausse', change_text)
            c.metric('RVOL quotidien approx.', f'{r["rvol"]:.2f}x' if r['rvol'] is not None else 'N/D')
            d.metric('Float', 'N/D')
            st.write('**Volume :**', f'{r["vol"]:,.0f}' if isinstance(r['vol'],(int,float)) else 'N/D')
            st.write('**BoursoBank :** à vérifier manuellement (fiche trouvée ≠ action négociable).')
            boursourl = 'https://www.google.com/search?' + urlencode({'q': f'site:boursorama.com/cours/ {r["ticker"]} stock'})
            tvsymbol = quote(f'{r["exchange"]}:{r["ticker"]}', safe=':')
            st.markdown(f'[Chercher sur BoursoBank]({boursourl}) · [Graphique TradingView](https://www.tradingview.com/chart/?symbol={tvsymbol})')
            st.markdown('**Actualités récentes (recherche Google News, non validées comme catalyseur) :**')
            articles = get_news(r['ticker'])
            if articles:
                for n in articles:
                    st.markdown(f'- [{n["title"]}]({n["link"]}) — {n["date"]}')
            else:
                st.write('Aucune actualité accessible. Catalyseur non confirmé.')
    df = pd.DataFrame(rows).drop(columns=['tv_relative_volume'], errors='ignore')
    st.download_button('Exporter CSV', df.to_csv(index=False).encode('utf-8'), 'scanner.csv', 'text/csv')
elif not st.session_state.get('scan_error'):
    st.info('Clique sur « Lancer le scan réel ». Si aucun candidat ne correspond, diminue le seuil de hausse ou le RVOL. Aucun résultat n’est inventé.')

st.divider()
st.caption('Scanner expérimental à données publiques différées. Ne garantit ni la couverture exhaustive du marché US, ni le prémarket, ni un float < 10 M, ni une news causale. Ne constitue pas un conseil en investissement.')
