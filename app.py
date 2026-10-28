import streamlit as st
import yfinance as yf
from yfinance import EquityQuery as Q
from datetime import datetime, timezone
from urllib.parse import quote
import pandas as pd

st.set_page_config(page_title="Daily Momentum • Réel", page_icon="📈", layout="wide")
st.title("📈 Daily Momentum — Scanner réel")
st.caption("Actions US • Sources Yahoo Finance via yfinance • Données pouvant être différées • Aucun compte requis pour consulter l'application déployée")
st.warning("Ce scanner utilise des cotations réelles fournies par un service tiers, pas un flux garanti temps réel. Les chiffres prémarket, le RVOL et la présence sur BoursoBank ne sont PAS certifiés. Aucune action fictive.")
with st.sidebar:
    st.header("Filtres")
    gain_min=st.slider("Hausse minimum (%)",0,50,10)
    price_min,price_max=st.slider("Prix ($)",0.5,50.0,(2.0,20.0),0.5)
    rvol_min=st.slider("Volume relatif minimum (approx.)",1.0,15.0,5.0,0.5)
    float_max=st.number_input("Float maximum (millions)",1,100,10)
    strict=st.checkbox("Mode strict (exclure valeurs inconnues)",False)
    limit=st.slider("Candidats à analyser",10,100,40,10)
    st.caption("Le RVOL approximatif = volume de séance / volume quotidien moyen sur 3 mois. Ce n'est PAS un RVOL normalisé à l'heure du jour.")
if "results" not in st.session_state: st.session_state.results=[]
if st.button("🔎 Lancer le scan réel",type="primary"):
    with st.spinner("Recherche des valeurs US et de leurs actualités…"):
        try:
            query=Q("and",[
                Q("eq",["region","us"]),
                Q("gte",["intradayprice",price_min]),
                Q("lte",["intradayprice",price_max]),
                Q("gte",["percentchange",gain_min]),
                Q("gte",["dayvolume",10000]),
            ])
            response=yf.screen(query,size=limit,sortField="percentchange",sortAsc=False)
            quotes=response.get("quotes",[])
            rows=[]
            for q in quotes:
                sym=q.get("symbol")
                if not sym: continue
                price=q.get("regularMarketPrice") or q.get("intradayprice")
                change=q.get("regularMarketChangePercent") or q.get("percentchange")
                vol=q.get("regularMarketVolume") or q.get("dayvolume")
                avg=q.get("averageDailyVolume3Month") or q.get("avgdailyvol3m")
                rvol=(vol/avg) if vol and avg else None
                if rvol is not None and rvol < rvol_min: continue
                if strict and rvol is None: continue
                rows.append({"ticker":sym,"name":q.get("shortName") or q.get("longName") or sym,
                    "price":price,"change":change,"vol":vol,"rvol":rvol,"float":None,
                    "news":[],"error":None})
            for r in rows[:25]:
                try:
                    t=yf.Ticker(r["ticker"])
                    info=t.get_info()
                    r["float"]=info.get("floatShares")
                    if strict and (r["float"] is None or r["float"] >= float_max*1_000_000): continue
                    articles=t.news or []
                    for entry in articles[:8]:
                        c=entry.get("content",entry)
                        title=c.get("title") or entry.get("title")
                        link=(c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or entry.get("link")
                        pub=c.get("pubDate") or c.get("displayTime") or entry.get("providerPublishTime")
                        summary=c.get("summary") or c.get("description") or ""
                        if title: r["news"].append({"title":title,"link":link,"date":pub,"summary":summary})
                except Exception as e:
                    r["error"]=str(e)
            st.session_state.results=rows
            st.session_state.scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception as e:
            st.error(f"Source de données indisponible ou limite d'accès atteinte : {e}")
rows=st.session_state.results
if rows:
    st.success(f"{len(rows)} valeurs candidates • Dernière requête : {st.session_state.get('scanned_at','—')}")
    st.info("BoursoBank : statut « à vérifier » par défaut. Une fiche de cours BoursoBank ne garantit pas que l'action soit négociable sur ton compte.")
    for r in rows:
        fl=r["float"]
        eligible=fl is not None and fl < float_max*1_000_000
        grade="B" if eligible and r["news"] else "C"
        with st.expander(f'{r["ticker"]} • {r["name"]} • {r["change"] or 0:+.1f}% • Classe {grade}',expanded=True):
            a,b,c,d=st.columns(4)
            a.metric("Cours",f'${r["price"]:.2f}' if isinstance(r["price"],(int,float)) else "N/D")
            b.metric("Hausse",f'{r["change"]:+.1f}%' if isinstance(r["change"],(int,float)) else "N/D")
            c.metric("RVOL approx.",f'{r["rvol"]:.2f}x' if r["rvol"] is not None else "N/D")
            d.metric("Float",f'{fl/1e6:.2f} M' if fl is not None else "N/D")
            st.write("**Volume :**",f'{r["vol"]:,}' if r["vol"] is not None else "N/D")
            st.write("**BoursoBank :** à vérifier manuellement")
            st.markdown(f'[Rechercher {r["ticker"]} sur BoursoBank](https://www.google.com/search?q={quote("site:boursorama.com/cours/ "+r["ticker"])}) · [Voir sur TradingView](https://www.tradingview.com/symbols/{quote(r["ticker"])}/)')
            st.markdown("**Actualités fournies par la source :**")
            if r["news"]:
                for n in r["news"]:
                    st.markdown(f'- **{n["title"]}** — {n["date"] or "date inconnue"}' + (f' · [Source]({n["link"]})' if n["link"] else ""))
                    if n["summary"]: st.caption(n["summary"][:700])
                st.caption("Les titres et résumés ne prouvent pas que ces news expliquent la hausse. Vérifier les annonces officielles et leur date avant tout trade.")
            else: st.write("Aucune news accessible via cette source ; catalyseur non confirmé.")
            if r["error"]: st.caption("Certaines données sont indisponibles.")
    df=pd.DataFrame([{k:r[k] for k in ["ticker","name","price","change","vol","rvol","float"]} for r in rows])
    st.download_button("Exporter CSV",df.to_csv(index=False).encode(),"scanner.csv","text/csv")
else:
    st.info("Clique sur « Lancer le scan réel ». Si aucun résultat n'apparaît, réduis le seuil RVOL ou la hausse minimale.")
st.divider()
st.caption("Important : screener Yahoo souvent centré sur la séance régulière ; couverture prémarket incomplète. Aucun niveau de support/résistance ni détail de news n'est inventé. Pour du vrai temps réel prémarket, il faut un fournisseur de données adapté.")
