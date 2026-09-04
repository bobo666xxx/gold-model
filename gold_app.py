
# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="黄金走势多因子分析模型 v2.0", page_icon="★", layout="wide", initial_sidebar_state="expanded")
st.sidebar.title("★ 黄金分析模型 v2.0")
st.sidebar.info("数据来源: Yahoo Finance + FRED\n全部免费, 无需 API Key")
st.sidebar.caption(f"数据更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.sidebar.divider()
st.sidebar.markdown("**模型说明:**\n- 15个核心因子加权评分\n- 短/中/长期趋势分析\n- 技术面指标(RSI/MACD/布林带)\n- 4种情景推演\n- 可下载完整报告")

# ============ 数据获取 ============

@st.cache_data(ttl=600)
def fetch_market_data():
    try:
        tickers = {
            "gold": "GC=F", "dxy": "DX-Y.NYB", "us10y": "TMUS10Y",
            "vix": "VIXY", "silver": "SI=F", "oil": "CL=F",
            "btc": "BTC-USD", "sp500": "^GSPC", "corn": "CC=F", "copper": "HG=F",
        }
        data = {}
        for name, ticker in tickers.items():
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="12mo")
                if not hist.empty:
                    data[name] = hist
            except Exception:
                continue
        return data
    except Exception as e:
        st.error(f"市场数据获取异常: {e}")
        return {}

@st.cache_data(ttl=600)
def fetch_fred_data(series_id):
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_all_macro_data():
    series = {
        "cpi": "CPIAUCSL", "core_cpi": "CPILFESL", "ppi": "PPIACO",
        "unemp": "UNRATE", "fed_rate": "FEDFUNDS", "nfp": "PAYEMS",
        "retail": "RSXFSN", "indprod": "INDPRO", "debt": "GFDEBTN",
        "m2": "M2SL", "consumer_conf": "UMCSENT", "housing": "HOUST",
    }
    result = {}
    for key, sid in series.items():
        df = fetch_fred_data(sid)
        if not df.empty:
            result[key] = df
    return result

# ============ 评分引擎 ============

def calculate_factor_scores(market_data, macro):
    scores = {}
    details = {}

    # 1. 美元指数
    if "dxy" in market_data and len(market_data["dxy"]) > 20:
        dxy = market_data["dxy"]["Close"]
        dxy_cur = dxy.iloc[-1]
        dxy_1m = (dxy.iloc[-1] / dxy.iloc[-22] - 1) * 100 if len(dxy) > 22 else 0
        dxy_3m = (dxy.iloc[-1] / dxy.iloc[-66] - 1) * 100 if len(dxy) > 66 else 0
        score = np.clip(-dxy_1m * 15, -100, 100)
        scores["美元指数"] = score
        details["美元指数"] = f"当前: {dxy_cur:.2f} | 1月: {dxy_1m:+.2f}% | 3月: {dxy_3m:+.2f}%"
    else:
        scores["美元指数"] = 0
        details["美元指数"] = "数据不可用"

    # 2. 实际利率
    if "us10y" in market_data and "cpi" in macro:
        us10y = market_data["us10y"]["Close"].iloc[-1]
        cpi_yoy = macro["cpi"]["CPIAUCSL"].pct_change(12).dropna()
        cpi_val = cpi_yoy.iloc[-1] if not cpi_yoy.empty else 3.0
        real_rate = us10y - cpi_val
        score = np.clip(abs(real_rate) * 20, 0, 100) if real_rate < 0 else np.clip(-real_rate * 15, -100, 0)
        scores["实际利率"] = score
        details["实际利率"] = f"10Y国债: {us10y:.2f}% | CPI同比: {cpi_val:.2f}% | 实际利率: {real_rate:.2f}%"
    else:
        scores["实际利率"] = 0
        details["实际利率"] = "数据不可用"

    # 3. 通胀数据
    if "cpi" in macro:
        cpi_yoy = macro["cpi"]["CPIAUCSL"].pct_change(12).dropna()
        if not cpi_yoy.empty:
            cur = cpi_yoy.iloc[-1]
            trend = cpi_yoy.iloc[-1] - cpi_yoy.iloc[-2] if len(cpi_yoy) > 1 else 0
            score = np.clip((cur - 2.0) * 25 + trend * 10, -100, 100)
            scores["通胀数据"] = score
            details["通胀数据"] = f"CPI同比: {cur:.2f}% | 趋势: {'上升' if trend > 0 else '下降'}({trend:+.2f}%)"
        else:
            scores["通胀数据"] = 0
            details["通胀数据"] = "数据不足"
    else:
        scores["通胀数据"] = 0
        details["通胀数据"] = "数据不可用"

    # 4. 核心CPI
    if "core_cpi" in macro:
        core_cpi = macro["core_cpi"]["CPILFESL"].pct_change(12).dropna()
        if not core_cpi.empty:
            cur_core = core_cpi.iloc[-1]
            core_trend = core_cpi.iloc[-1] - core_cpi.iloc[-2] if len(core_cpi) > 1 else 0
            score = np.clip((cur_core - 2.0) * 20 + core_trend * 8, -100, 100)
            scores["核心CPI"] = score
            details["核心CPI"] = f"核心CPI同比: {cur_core:.2f}% | 趋势: {'上升' if core_trend > 0 else '下降'}({core_trend:+.2f}%)"
        else:
            scores["核心CPI"] = 0
            details["核心CPI"] = "数据不足"
    else:
        scores["核心CPI"] = 0
        details["核心CPI"] = "数据不足"

    # 5. PPI
    if "ppi" in macro:
        ppi = macro["ppi"]["PPIACO"].pct_change(12).dropna()
        if not ppi.empty:
            cur_ppi = ppi.iloc[-1]
            ppi_trend = ppi.iloc[-1] - ppi.iloc[-2] if len(ppi) > 1 else 0
            score = np.clip((cur_ppi - 1.5) * 20 + ppi_trend * 8, -100, 100)
            scores["PPI"] = score
            details["PPI"] = f"PPI同比: {cur_ppi:.2f}% | 趋势: {'上升' if ppi_trend > 0 else '下降'}({ppi_trend:+.2f}%)"
        else:
            scores["PPI"] = 0
            details["PPI"] = "数据不足"
    else:
        scores["PPI"] = 0
        details["PPI"] = "数据不足"

    # 6. 就业数据(非农)
    if "nfp" in macro:
        nfp = macro["nfp"]["PAYEMS"].diff().dropna()
        if not nfp.empty:
            latest = nfp.iloc[-1]
            avg_12 = nfp.iloc[-12:].mean() if len(nfp) >= 12 else nfp.mean()
            dev = latest - avg_12
            score = np.clip(-dev / 50, -100, 100)
            scores["就业数据(非农)"] = score
            details["就业数据(非农)"] = f"最新非农: {latest:+.0f}K | 12月均值: {avg_12:+.0f}K | 偏差: {dev:+.0f}K"
        else:
            scores["就业数据(非农)"] = 0
            details["就业数据(非农)"] = "数据不足"
    else:
        scores["就业数据(非农)"] = 0
        details["就业数据(非农)"] = "数据不足"

    # 7. 失业率
    if "unemp" in macro:
        unemp = macro["unemp"]["UNRATE"].dropna()
        if not unemp.empty:
            cur = unemp.iloc[-1]
            chg = unemp.iloc[-1] - unemp.iloc[-2] if len(unemp) > 1 else 0
            score = np.clip((cur - 3.5) * 30 + chg * 50, -100, 100)
            scores["失业率"] = score
            details["失业率"] = f"当前: {cur:.1f}% | 变动: {chg:+.2f}%"
        else:
            scores["失业率"] = 0
            details["失业率"] = "数据不足"
    else:
        scores["失业率"] = 0
        details["失业率"] = "数据不足"

    # 8. 美联储利率
    if "fed_rate" in macro:
        fed = macro["fed_rate"]["FEDFUNDS"].dropna()
        if not fed.empty:
            cur = fed.iloc[-1]
            chg = fed.iloc[-1] - fed.iloc[-2] if len(fed) > 1 else 0
            if chg < 0:
                score = np.clip(abs(chg) * 40, 0, 100)
            elif chg > 0:
                score = np.clip(-abs(chg) * 40, -100, 0)
            else:
                score = 20
            scores["美联储利率"] = score
            details["美联储利率"] = f"联邦基金利率: {cur:.2f}% | 最近变动: {chg:+.2f}%"
        else:
            scores["美联储利率"] = 0
            details["美联储利率"] = "数据不足"
    else:
        scores["美联储利率"] = 0
        details["美联储利率"] = "数据不足"

    # 9. 消费指数
    if "retail" in macro:
        retail = macro["retail"]["RSXFSN"].dropna()
        if len(retail) > 12:
            chg = (retail.iloc[-1] / retail.iloc[-13] - 1) * 100
            score = np.clip(-chg * 10, -100, 100)
            scores["消费指数"] = score
            details["消费指数"] = f"零售销售12月变动: {chg:+.2f}%"
        else:
            scores["消费指数"] = 0
            details["消费指数"] = "数据不足"
    else:
        scores["消费指数"] = 0
        details["消费指数"] = "数据不足"

    # 10. 工业生产
    if "indprod" in macro:
        indprod = macro["indprod"]["INDPRO"].dropna()
        if len(indprod) > 12:
            chg = (indprod.iloc[-1] / indprod.iloc[-13] - 1) * 100
            score = np.clip(-chg * 10, -100, 100)
            scores["生产指数"] = score
            details["生产指数"] = f"工业生产12月变动: {chg:+.2f}%"
        else:
            scores["生产指数"] = 0
            details["生产指数"] = "数据不足"
    else:
        scores["生产指数"] = 0
        details["生产指数"] = "数据不足"

    # 11. VIX恐慌指数
    if "vix" in market_data and len(market_data["vix"]) > 5:
        vix = market_data["vix"]["Close"]
        cur_vix = vix.iloc[-1]
        avg_vix = vix.iloc[-22:].mean() if len(vix) > 22 else vix.mean()
        score = np.clip((cur_vix - 20) * 3, -100, 100)
        scores["地缘/避险(VIX)"] = score
        details["地缘/避险(VIX)"] = f"VIX当前: {cur_vix:.1f} | 20日均值: {avg_vix:.1f}"
    else:
        scores["地缘/避险(VIX)"] = 0
        details["地缘/避险(VIX)"] = "数据不可用"

    # 12. 央行购金/避险
    if "gold" in market_data and "silver" in market_data:
        gold_p = market_data["gold"]["Close"].iloc[-1]
        silver_p = market_data["silver"]["Close"].iloc[-1]
        ratio = gold_p / silver_p if silver_p > 0 else 80
        score = np.clip((ratio - 80) * 2, -100, 100)
        scores["央行购金/避险"] = score
        details["央行购金/避险"] = f"金银比: {ratio:.1f} | 黄金: ${gold_p:.2f} | 白银: ${silver_p:.2f}"
    else:
        scores["央行购金/避险"] = 0
        details["央行购金/避险"] = "数据不可用"

    # 13. 美国负债
    if "debt" in macro:
        debt = macro["debt"]["GFDEBTN"].dropna()
        if len(debt) > 4:
            chg = (debt.iloc[-1] / debt.iloc[-2] - 1) * 100 if len(debt) > 1 else 0
            score = np.clip(chg * 5 + 30, -100, 100)
            scores["美国负债"] = score
            details["美国负债"] = f"国债总额: ${debt.iloc[-1]/1e9:.0f}B | 季度变动: {chg:+.2f}%"
        else:
            scores["美国负债"] = 0
            details["美国负债"] = "数据不足"
    else:
        scores["美国负债"] = 0
        details["美国负债"] = "数据不足"

    # 14. M2货币供应
    if "m2" in macro:
        m2 = macro["m2"]["M2SL"].dropna()
        if len(m2) > 12:
            m2_chg = (m2.iloc[-1] / m2.iloc[-13] - 1) * 100
            score = np.clip(m2_chg * 8, -100, 100)
            scores["M2货币供应"] = score
            details["M2货币供应"] = f"M2同比变动: {m2_chg:+.2f}%"
        else:
            scores["M2货币供应"] = 0
            details["M2货币供应"] = "数据不足"
    else:
        scores["M2货币供应"] = 0
        details["M2货币供应"] = "数据不足"

    # 15. 消费者信心
    if "consumer_conf" in macro:
        cc = macro["consumer_conf"]["UMCSENT"].dropna()
        if len(cc) > 12:
            cc_chg = (cc.iloc[-1] / cc.iloc[-13] - 1) * 100
            score = np.clip(-cc_chg * 5, -100, 100)
            scores["消费者信心"] = score
            details["消费者信心"] = f"信心指数12月变动: {cc_chg:+.2f}%"
        else:
            scores["消费者信心"] = 0
            details["消费者信心"] = "数据不足"
    else:
        scores["消费者信心"] = 0
        details["消费者信心"] = "数据不足"

    return scores, details

def calculate_composite_score(scores):
    weights = {
        "美元指数": 0.12, "实际利率": 0.15, "通胀数据": 0.10,
        "核心CPI": 0.08, "PPI": 0.05, "就业数据(非农)": 0.08,
        "失业率": 0.06, "美联储利率": 0.10, "消费指数": 0.04,
        "生产指数": 0.04, "地缘/避险(VIX)": 0.05,
        "央行购金/避险": 0.05, "美国负债": 0.05,
        "M2货币供应": 0.05, "消费者信心": 0.03,
    }
    total_weight = 0
    weighted_sum = 0
    for factor, score in scores.items():
        w = weights.get(factor, 0.05)
        weighted_sum += score * w
        total_weight += w
    return weighted_sum / total_weight if total_weight > 0 else 0

def get_signal(composite):
    if composite > 50:
        return "强烈看多", "green"
    elif composite > 20:
        return "偏多", "limegreen"
    elif composite > -20:
        return "中性震荡", "gold"
    elif composite > -50:
        return "偏空", "orange"
    else:
        return "强烈看空", "red"

# ============ 技术面分析 ============

def calculate_technical_indicators(market_data):
    tech = {}
    if "gold" not in market_data:
        return tech
    gold = market_data["gold"]["Close"]
    tech["price"] = gold.iloc[-1]
    tech["price_1d"] = gold.iloc[-2] if len(gold) > 1 else gold.iloc[-1]
    tech["price_1w"] = gold.iloc[-5] if len(gold) > 5 else gold.iloc[-1]
    tech["price_1m"] = gold.iloc[-22] if len(gold) > 22 else gold.iloc[-1]
    tech["price_3m"] = gold.iloc[-66] if len(gold) > 66 else gold.iloc[-1]
    tech["MA5"] = gold.rolling(5).mean().iloc[-1] if len(gold) >= 5 else gold.iloc[-1]
    tech["MA10"] = gold.rolling(10).mean().iloc[-1] if len(gold) >= 10 else gold.iloc[-1]
    tech["MA20"] = gold.rolling(20).mean().iloc[-1] if len(gold) >= 20 else gold.iloc[-1]
    tech["MA50"] = gold.rolling(50).mean().iloc[-1] if len(gold) >= 50 else gold.iloc[-1]
    tech["MA200"] = gold.rolling(200).mean().iloc[-1] if len(gold) >= 200 else gold.iloc[-1]
    delta = gold.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    if loss.iloc[-1] != 0:
        rs = gain.iloc[-1] / loss.iloc[-1]
        tech["RSI"] = 100 - (100 / (1 + rs))
    else:
        tech["RSI"] = 50
    ema12 = gold.ewm(span=12).mean()
    ema26 = gold.ewm(span=26).mean()
    tech["MACD"] = ema12.iloc[-1] - ema26.iloc[-1]
    tech["MACD_signal"] = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
    tech["BB_middle"] = tech["MA20"]
    bb_std = gold.rolling(20).std().iloc[-1] if len(gold) >= 20 else 0
    tech["BB_upper"] = tech["MA20"] + 2 * bb_std
    tech["BB_lower"] = tech["MA20"] - 2 * bb_std
    return tech

# ============ 短/中/长期趋势分析 ============

def analyze_trends(scores, tech, market_data):
    analysis = {}
    # 短期
    short_factors = []
    if "美元指数" in scores:
        short_factors.append("美元" + ("走强施压金价" if scores["美元指数"] > 0 else "走弱支撑金价"))
    if "实际利率" in scores:
        short_factors.append("实际利率" + ("上行压制黄金" if scores["实际利率"] > 0 else "下行利好黄金"))
    if "地缘/避险(VIX)" in scores:
        short_factors.append("避险情绪" + ("升温" if scores["地缘/避险(VIX)"] > 0 else "平稳"))
    if "美联储利率" in scores:
        short_factors.append("降息预期" + ("升温" if scores["美联储利率"] > 0 else "或维持高利率"))
    if tech:
        if tech.get("RSI", 50) > 70:
            short_factors.append("RSI超买，短期可能回调")
        elif tech.get("RSI", 50) < 30:
            short_factors.append("RSI超卖，短期可能反弹")
        if tech.get("MACD", 0) > tech.get("MACD_signal", 0):
            short_factors.append("MACD金叉，短期偏多")
        else:
            short_factors.append("MACD死叉，短期偏空")
    analysis["短期(1-3个月)"] = {"factors": short_factors, "rsi": tech.get("RSI", None), "macd": tech.get("MACD", None), "macd_signal": tech.get("MACD_signal", None)}

    # 中期
    mid_factors = []
    if "通胀数据" in scores:
        mid_factors.append("通胀" + ("粘性支撑黄金" if scores["通胀数据"] > 0 else "回落压力"))
    if "就业数据(非农)" in scores:
        mid_factors.append("就业" + ("市场稳健" if scores["就业数据(非农)"] > 0 else "放缓，降息预期增强"))
    if "美联储利率" in scores:
        mid_factors.append("美联储" + ("转向降息周期" if scores["美联储利率"] > 0 else "维持紧缩政策"))
    if "消费指数" in scores:
        mid_factors.append("消费" + ("韧性较强" if scores["消费指数"] > 0 else "疲软，经济放缓风险"))
    if "生产指数" in scores:
        mid_factors.append("工业" + ("产出稳定" if scores["生产指数"] > 0 else "产出下滑"))
    analysis["中期(3-12个月)"] = {"factors": mid_factors}

    # 长期
    long_factors = []
    if "美国负债" in scores:
        long_factors.append("美国债务持续扩张，美元信用长期承压" if scores["美国负债"] > 0 else "美国债务增速放缓")
    if "M2货币供应" in scores:
        long_factors.append("货币超发趋势延续，利好黄金" if scores["M2货币供应"] > 0 else "货币供应增速放缓")
    if "央行购金/避险" in scores:
        long_factors.append("全球央行持续购金，结构性需求支撑" if scores["央行购金/避险"] > 0 else "央行购金需求减弱")
    long_factors.extend(["去美元化趋势长期利好黄金", "地缘政治不确定性长期存在"])
    analysis["长期(1-5年)"] = {"factors": long_factors}
    return analysis

# ============ 主界面 ============

with st.spinner("正在获取数据并计算评分..."):
    market_data = fetch_market_data()
    macro = fetch_all_macro_data()

if not market_data:
    st.error("所有市场数据获取失败，请检查网络连接。")
    st.stop()

scores, details = calculate_factor_scores(market_data, macro)
composite = calculate_composite_score(scores)
signal, signal_color = get_signal(composite)
tech = calculate_technical_indicators(market_data)
trend_analysis = analyze_trends(scores, tech, market_data)

# 顶部概览
st.title("★ 黄金走势多因子分析模型 v2.0")
st.caption("数据来源: Yahoo Finance + FRED (全部免费, 无需 API Key)")

col1, col2, col3, col4 = st.columns(4)
if "gold" in market_data:
    gold_price = market_data["gold"]["Close"].iloc[-1]
    gold_chg_1d = (market_data["gold"]["Close"].iloc[-1] / market_data["gold"]["Close"].iloc[-2] - 1) * 100
    col1.metric("黄金价格", f"${gold_price:.2f}", f"{gold_chg_1d:+.2f}%")
else:
    col1.metric("黄金价格", "N/A", "")
col2.metric("综合评分", f"{composite:+.1f} / 100", "")
col3.text(f"趋势信号\n{signal} ({signal_color})")
if "dxy" in market_data:
    col4.metric("美元指数", f"{market_data['dxy']['Close'].iloc[-1]:.2f}", "")

st.divider()

# 技术面指标
st.subheader("★ 技术面指标")
if tech:
    tech_cols = st.columns(8)
    items = [
        ("当前价", f"${tech['price']:.2f}"),
        ("1日涨跌", f"{(tech['price']/tech['price_1d']-1)*100:+.2f}%"),
        ("1周涨跌", f"{(tech['price']/tech['price_1w']-1)*100:+.2f}%"),
        ("1月涨跌", f"{(tech['price']/tech['price_1m']-1)*100:+.2f}%"),
        ("3月涨跌", f"{(tech['price']/tech['price_3m']-1)*100:+.2f}%"),
        ("RSI(14)", f"{tech['RSI']:.1f}"),
        ("MACD", f"{tech['MACD']:.2f}"),
        ("MA200", f"${tech['MA200']:.2f}"),
    ]
    for i, (label, val) in enumerate(items):
        tech_cols[i].metric(label, val)

    rsi_val = tech.get("RSI", 50)
    if rsi_val > 70:
        st.warning(f"RSI提示: 超买区域 ({rsi_val:.1f})，短期可能回调")
    elif rsi_val < 30:
        st.success(f"RSI提示: 超卖区域 ({rsi_val:.1f})，短期可能反弹")
    else:
        st.info(f"RSI提示: 中性区域 ({rsi_val:.1f})")

st.divider()

# 因子评分表
st.subheader("★ 各因子评分明细（15个核心因子）")
factor_names = list(scores.keys())
factor_values = list(scores.values())
factor_details = [details.get(f, "") for f in factor_names]

def factor_color(s):
    if s > 30: return "绿色"
    elif s > 0: return "浅绿"
    elif s > -30: return "黄色"
    else: return "红色"

table_data = []
for i, name in enumerate(factor_names):
    table_data.append({"因子": name, "评分": f"{factor_values[i]:+.1f}", "信号": factor_color(factor_values[i]), "详情": factor_details[i]})
df_table = pd.DataFrame(table_data)
st.table(df_table)

# 因子雷达图
st.subheader("★ 因子雷达图")
categories = factor_names
values = factor_values + [factor_values[0]]
fig_radar = go.Figure()
fig_radar.add_trace(go.Scatterpolar(r=values, theta=categories, fill='toself', fillcolor='rgba(255,165,0,0.3)', line_color='orange', name='当前评分'))
fig_radar.add_trace(go.Scatterpolar(r=[0]*len(categories), theta=categories, fill='toself', fillcolor='rgba(0,128,255,0.1)', line_color='blue', name='中性基准'))
fig_radar.update_layout(polar=dict(radialaxis=dict(range=[-100,100], tickfont=dict(size=10)), angularaxis=dict(tickfont=dict(size=10))), height=600, width=800)
st.plotly_chart(fig_radar, use_container_width=True)

# 因子得分柱状图
st.subheader("★ 各因子得分对比")
colors_bar = ["#2E7D32" if v > 0 else "#C62828" for v in factor_values]
fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(x=factor_names, y=factor_values, marker_color=colors_bar, text=[f"{v:+.1f}" for v in factor_values], textposition='auto'))
fig_bar.update_layout(xaxis_tickangle=-45, yaxis_title="评分", yaxis_range=[-100, 100], height=450)
st.plotly_chart(fig_bar, use_container_width=True)

# 因子贡献饼图
st.subheader("★ 因子贡献度（绝对值排序Top8）")
abs_scores = [(f, abs(v)) for f, v in scores.items()]
abs_scores.sort(key=lambda x: x[1], reverse=True)
top_factors = abs_scores[:8]
fig_pie = go.Figure()
fig_pie.add_trace(go.Pie(labels=[f[0] for f in top_factors], values=[f[1] for f in top_factors], hole=0.3, marker_colors=['#2E7D32' if scores[f[0]] > 0 else '#C62828' for f in top_factors]))
fig_pie.update_layout(height=400)
st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ============ 可视化模块 ============
st.subheader("★ 市场数据可视化")

# 金价K线图+技术指标
if "gold" in market_data:
    st.markdown("##### 金价走势与技术指标")
    gold = market_data["gold"]
    fig_gold = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            row_heights=[0.5, 0.2, 0.2], subplot_titles=["金价K线图", "成交量", "RSI"])
    fig_gold.add_trace(go.Candlestick(x=gold.index, open=gold["Open"], high=gold["High"], low=gold["Low"], close=gold["Close"], name="金价", increasing_line_color='#2E7D32', decreasing_line_color='#C62828'), row=1, col=1)
    if len(gold) >= 20:
        ma20 = gold["Close"].rolling(20).mean()
        fig_gold.add_trace(go.Scatter(x=gold.index, y=ma20, line=dict(color='#1565C0', width=1.5), name="MA20"), row=1, col=1)
    if len(gold) >= 50:
        ma50 = gold["Close"].rolling(50).mean()
        fig_gold.add_trace(go.Scatter(x=gold.index, y=ma50, line=dict(color='#E65100', width=1.5), name="MA50"), row=1, col=1)
    if len(gold) >= 20:
        ma20 = gold["Close"].rolling(20).mean()
        bb_std = gold["Close"].rolling(20).std()
        fig_gold.add_trace(go.Scatter(x=gold.index, y=ma20 + 2*bb_std, line=dict(color='#90CAF9', width=0.8), name="BB上轨"), row=1, col=1)
        fig_gold.add_trace(go.Scatter(x=gold.index, y=ma20 - 2*bb_std, line=dict(color='#90CAF9', width=0.8), name="BB下轨"), row=1, col=1)
    fig_gold.add_trace(go.Bar(x=gold.index, y=gold["Volume"], name="成交量", marker_color='#1565C0'), row=2, col=1)
    delta = gold["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    fig_gold.add_trace(go.Scatter(x=gold.index, y=rsi, line=dict(color='#E65100', width=1.5), name="RSI"), row=3, col=1)
    fig_gold.add_trace(go.Scatter(x=gold.index, y=[70]*len(gold.index), line=dict(color='#C62828', width=0.5, dash='dash'), name="超买"), row=3, col=1)
    fig_gold.add_trace(go.Scatter(x=gold.index, y=[30]*len(gold.index), line=dict(color='#2E7D32', width=0.5, dash='dash'), name="超卖"), row=3, col=1)
    fig_gold.update_layout(height=700, xaxis_title="日期", yaxis_title="美元/盎司")
    st.plotly_chart(fig_gold, use_container_width=True)

# 美元指数
if "dxy" in market_data:
    st.markdown("##### 美元指数走势（近12个月）")
    fig_dxy = go.Figure()
    fig_dxy.add_trace(go.Scatter(x=market_data["dxy"].index, y=market_data["dxy"]["Close"], line_color="#1565C0", name="美元指数"))
    if len(market_data["dxy"]) >= 20:
        ma20 = market_data["dxy"]["Close"].rolling(20).mean()
        fig_dxy.add_trace(go.Scatter(x=market_data["dxy"].index, y=ma20, line=dict(color='#E65100', width=1.5), name="MA20"))
    fig_dxy.update_layout(height=350, xaxis_title="日期", yaxis_title="美元指数")
    st.plotly_chart(fig_dxy, use_container_width=True)

# 实际利率
if "us10y" in market_data and "cpi" in macro:
    st.markdown("##### 10年期国债收益率 vs CPI同比 vs 实际利率")
    fig_real = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=["名义利率 vs CPI", "实际利率"])
    us10y_series = market_data["us10y"]["Close"]
    cpi_yoy = macro["cpi"]["CPIAUCSL"].pct_change(12)
    common_idx = us10y_series.index.intersection(cpi_yoy.dropna().index)
    if len(common_idx) > 0:
        fig_real.add_trace(go.Scatter(x=common_idx, y=us10y_series[common_idx], line_color='#E65100', name='10Y国债收益率'), row=1, col=1)
        fig_real.add_trace(go.Scatter(x=common_idx, y=cpi_yoy[common_idx], line_color='#1B5E20', name='CPI同比'), row=1, col=1)
        real_rate = us10y_series[common_idx] - cpi_yoy[common_idx]
        fig_real.add_trace(go.Scatter(x=common_idx, y=real_rate, line_color='#6A1B9A', name='实际利率'), row=2, col=1)
        fig_real.add_trace(go.Scatter(x=common_idx, y=[0]*len(common_idx), line=dict(color='#333', width=0.5), name='零轴'), row=2, col=1)
    fig_real.update_layout(height=500, xaxis_title="日期", yaxis_title="%")
    st.plotly_chart(fig_real, use_container_width=True)

# 金银比
if "gold" in market_data and "silver" in market_data:
    st.markdown("##### 金银比走势")
    gold_prices = market_data["gold"]["Close"]
    silver_prices = market_data["silver"]["Close"]
    common_idx = gold_prices.index.intersection(silver_prices.index)
    if len(common_idx) > 0:
        ratio = gold_prices[common_idx] / silver_prices[common_idx]
        fig_ratio = go.Figure()
        fig_ratio.add_trace(go.Scatter(x=common_idx, y=ratio, line_color='#FF8F00', name='金银比'))
        fig_ratio.add_trace(go.Scatter(x=common_idx, y=ratio.rolling(30).mean(), line_color='#1565C0', name='30日均值'))
        fig_ratio.add_hline(y=80, line_dash="dash", line_color="#C62828", annotation_text="80 (高)")
        fig_ratio.add_hline(y=60, line_dash="dash", line_color="#2E7D32", annotation_text="60 (低)")
        fig_ratio.update_layout(height=350, xaxis_title="日期", yaxis_title="金银比")
        st.plotly_chart(fig_ratio, use_container_width=True)

# 黄金 vs 比特币
if "gold" in market_data and "btc" in market_data:
    st.markdown("##### 黄金 vs 比特币（近12个月收益对比）")
    gold_returns = (market_data["gold"]["Close"] / market_data["gold"]["Close"].iloc[0] - 1) * 100
    btc_returns = (market_data["btc"]["Close"] / market_data["btc"]["Close"].iloc[0] - 1) * 100
    common_idx = gold_returns.index.intersection(btc_returns.index)
    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Scatter(x=common_idx, y=gold_returns[common_idx], line_color='#FF8F00', name='黄金'))
    fig_cmp.add_trace(go.Scatter(x=common_idx, y=btc_returns[common_idx], line_color='#1565C0', name='比特币'))
    fig_cmp.update_layout(height=350, xaxis_title="日期", yaxis_title="收益率(%)")
    st.plotly_chart(fig_cmp, use_container_width=True)

# 油价
if "oil" in market_data:
    st.markdown("##### 原油WTI价格走势（近12个月）")
    fig_oil = go.Figure()
    fig_oil.add_trace(go.Scatter(x=market_data["oil"].index, y=market_data["oil"]["Close"], line_color='#333333', name='WTI原油'))
    fig_oil.update_layout(height=350, xaxis_title="日期", yaxis_title="美元/桶")
    st.plotly_chart(fig_oil, use_container_width=True)

# 铜价
if "copper" in market_data:
    st.markdown("##### 铜期货价格走势（近12个月）")
    fig_cu = go.Figure()
    fig_cu.add_trace(go.Scatter(x=market_data["copper"].index, y=market_data["copper"]["Close"], line_color='#D2691E', name='铜'))
    fig_cu.update_layout(height=350, xaxis_title="日期", yaxis_title="美元/磅")
    st.plotly_chart(fig_cu, use_container_width=True)

st.divider()

# ============ 宏观数据面板 ============
st.subheader("★ 宏观数据面板")
if "cpi" in macro:
    cpi_yoy = macro["cpi"]["CPIAUCSL"].pct_change(12).dropna()
    st.markdown(f"**CPI同比**: 当前 {cpi_yoy.iloc[-1]:.2f}% | 12月均值: {cpi_yoy.iloc[-12:].mean():.2f}% | 最高: {cpi_yoy.max():.2f}% | 最低: {cpi_yoy.min():.2f}%")
if "core_cpi" in macro:
    core_cpi = macro["core_cpi"]["CPILFESL"].pct_change(12).dropna()
    if not core_cpi.empty:
        st.markdown(f"**核心CPI同比**: 当前 {core_cpi.iloc[-1]:.2f}% | 12月均值: {core_cpi.iloc[-12:].mean():.2f}%")
if "ppi" in macro:
    ppi = macro["ppi"]["PPIACO"].pct_change(12).dropna()
    if not ppi.empty:
        st.markdown(f"**PPI同比**: 当前 {ppi.iloc[-1]:.2f}% | 12月均值: {ppi.iloc[-12:].mean():.2f}%")
if "unemp" in macro:
    unemp = macro["unemp"]["UNRATE"].dropna()
    st.markdown(f"**失业率**: 当前 {unemp.iloc[-1]:.1f}% | 12月均值: {unemp.iloc[-12:].mean():.1f}% | 最高: {unemp.max():.1f}% | 最低: {unemp.min():.1f}%")
if "fed_rate" in macro:
    fed = macro["fed_rate"]["FEDFUNDS"].dropna()
    st.markdown(f"**联邦基金利率**: 当前 {fed.iloc[-1]:.2f}% | 最近变动: {fed.iloc[-1]-fed.iloc[-2]:+.2f}%")
if "nfp" in macro:
    nfp = macro["nfp"]["PAYEMS"].diff().dropna()
    st.markdown(f"**非农就业**: 最新 {nfp.iloc[-1]:+.0f}K | 12月均值: {nfp.iloc[-12:].mean():+.0f}K")
if "debt" in macro:
    debt = macro["debt"]["GFDEBTN"].dropna()
    st.markdown(f"**美国国债**: ${debt.iloc[-1]/1e9:.0f}B | 季度变动: {(debt.iloc[-1]/debt.iloc[-2]-1)*100:+.2f}%")
if "retail" in macro:
    retail = macro["retail"]["RSXFSN"].dropna()
    if len(retail) > 12:
        st.markdown(f"**零售销售**: 12月变动 {(retail.iloc[-1]/retail.iloc[-13]-1)*100:+.2f}%")
if "indprod" in macro:
    indprod = macro["indprod"]["INDPRO"].dropna()
    if len(indprod) > 12:
        st.markdown(f"**工业生产**: 12月变动 {(indprod.iloc[-1]/indprod.iloc[-13]-1)*100:+.2f}%")
if "m2" in macro:
    m2 = macro["m2"]["M2SL"].dropna()
    if len(m2) > 12:
        st.markdown(f"**M2货币供应**: 12月变动 {(m2.iloc[-1]/m2.iloc[-13]-1)*100:+.2f}%")
if "consumer_conf" in macro:
    cc = macro["consumer_conf"]["UMCSENT"].dropna()
    if len(cc) > 12:
        st.markdown(f"**消费者信心**: 当前 {cc.iloc[-1]:.1f} | 12月变动: {(cc.iloc[-1]/cc.iloc[-13]-1)*100:+.2f}%")

st.divider()

# ============ 短/中/长期趋势总结 ============
st.subheader("★ 黄金趋势总结")

st.markdown("### 短期趋势（1-3个月）")
st.markdown("**当前技术面状态:**")
if tech:
    st.markdown(f"- RSI(14): {tech['RSI']:.1f} {'(超买)' if tech['RSI'] > 70 else '(超卖)' if tech['RSI'] < 30 else '(中性)'}")
    st.markdown(f"- MACD: {tech['MACD']:.2f} vs 信号线: {tech['MACD_signal']:.2f} {'(金叉偏多)' if tech['MACD'] > tech['MACD_signal'] else '(死叉偏空)'}")
    st.markdown(f"- 布林带: 上轨 ${tech['BB_upper']:.2f} / 中轨 ${tech['BB_middle']:.2f} / 下轨 ${tech['BB_lower']:.2f}")
    st.markdown(f"- 当前价 ${tech['price']:.2f} {'(接近上轨，注意回调风险)' if tech['price'] > tech['BB_upper'] * 0.98 else '(接近下轨，关注反弹机会)' if tech['price'] < tech['BB_lower'] * 1.02 else '(区间中部)'}")
    st.markdown(f"- MA20: ${tech['MA20']:.2f} | MA50: ${tech['MA50']:.2f} | MA200: ${tech['MA200']:.2f}")

st.markdown("**短期驱动因素:**")
for f in trend_analysis["短期(1-3个月)"]["factors"]:
    st.markdown(f"- {f}")

st.markdown("### 中期趋势（3-12个月）")
st.markdown("**中期驱动因素:**")
for f in trend_analysis["中期(3-12个月)"]["factors"]:
    st.markdown(f"- {f}")

st.markdown("### 长期趋势（1-5年）")
st.markdown("**长期驱动因素:**")
for f in trend_analysis["长期(1-5年)"]["factors"]:
    st.markdown(f"- {f}")

st.divider()

# ============ 情景推演 ============
st.subheader("★ 情景推演")

scenarios = [
    {"name": "美联储降息周期开启", "美元指数": -30, "实际利率": 40, "通胀数据": 0, "核心CPI": 0, "PPI": 0, "就业数据(非农)": 20, "失业率": 0, "美联储利率": 50, "消费指数": 10, "生产指数": 10, "地缘/避险(VIX)": 0, "央行购金/避险": 0, "美国负债": 10, "M2货币供应": 10, "消费者信心": 10},
    {"name": "美国经济衰退", "美元指数": -20, "实际利率": -30, "通胀数据": -40, "核心CPI": -30, "PPI": -30, "就业数据(非农)": -50, "失业率": 0, "美联储利率": 40, "消费指数": -40, "生产指数": -40, "地缘/避险(VIX)": 40, "央行购金/避险": 20, "美国负债": 20, "M2货币供应": -20, "消费者信心": -40},
    {"name": "地缘政治危机升级", "美元指数": 10, "实际利率": 0, "通胀数据": 30, "核心CPI": 20, "PPI": 20, "就业数据(非农)": 0, "失业率": 0, "美联储利率": 0, "消费指数": -20, "生产指数": -20, "地缘/避险(VIX)": 60, "央行购金/避险": 40, "美国负债": 10, "M2货币供应": 0, "消费者信心": -30},
    {"name": "美国经济软着陆", "美元指数": 20, "实际利率": 20, "通胀数据": 10, "核心CPI": 10, "PPI": 10, "就业数据(非农)": 10, "失业率": 0, "美联储利率": 0, "消费指数": 20, "生产指数": 20, "地缘/避险(VIX)": -20, "央行购金/避险": -10, "美国负债": 10, "M2货币供应": 10, "消费者信心": 20},
]

weights = {"美元指数": 0.12, "实际利率": 0.15, "通胀数据": 0.10, "核心CPI": 0.08, "PPI": 0.05, "就业数据(非农)": 0.08, "失业率": 0.06, "美联储利率": 0.10, "消费指数": 0.04, "生产指数": 0.04, "地缘/避险(VIX)": 0.05, "央行购金/避险": 0.05, "美国负债": 0.05, "M2货币供应": 0.05, "消费者信心": 0.03}

scenario_results = []
for sc in scenarios:
    total_w = 0
    weighted = 0
    for k, v in sc.items():
        if k == "name": continue
        w = weights.get(k, 0.05)
        weighted += v * w
        total_w += w
    sc_score = weighted / total_w if total_w > 0 else 0
    sc_signal, _ = get_signal(sc_score)
    scenario_results.append({"情景": sc["name"], "综合评分": f"{sc_score:+.1f}", "信号": sc_signal})

df_scenario = pd.DataFrame(scenario_results)
st.table(df_scenario)

st.divider()
st.caption("免责声明: 本模型仅用于学习和研究目的，不构成任何投资建议。数据来源于公开免费接口，可能存在延迟或误差。投资有风险，入市需谨慎。")

# 下载报告
def generate_report_text(scores, details, composite, signal, market_data, macro, tech, trend_analysis):
    lines = []
    lines.append("=" * 60)
    lines.append(" 黄金走势多因子分析报告 v2.0")
    lines.append(f" 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")
    if "gold" in market_data:
        gold_price = market_data["gold"]["Close"].iloc[-1]
        gold_chg = (market_data["gold"]["Close"].iloc[-1] / market_data["gold"]["Close"].iloc[-2] - 1) * 100
        lines.append(f" 当前金价: ${gold_price:.2f}/盎司 ({gold_chg:+.2f}%)")
    lines.append(f" 综合评分: {composite:+.1f} / 100")
    lines.append(f" 趋势信号: {signal}")
    lines.append("")
    lines.append("-" * 60)
    lines.append(" 各因子评分明细:")
    lines.append("-" * 60)
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for i, (factor, score) in enumerate(sorted_items, 1):
        marker = "绿色" if score > 30 else ("浅绿" if score > 0 else ("黄色" if score > -30 else "红色"))
        detail = details.get(factor, "")
        lines.append(f"  {i}. {factor}: {score:+.1f} 分 [{marker}]")
        lines.append(f"     详情: {detail}")
        lines.append("")
    lines.append("-" * 60)
    lines.append(" 技术面指标:")
    lines.append("-" * 60)
    if tech:
        lines.append(f"  RSI(14): {tech.get('RSI', 'N/A')}")
        lines.append(f"  MACD: {tech.get('MACD', 'N/A')}")
        lines.append(f"  MACD信号线: {tech.get('MACD_signal', 'N/A')}")
        lines.append(f"  布林上轨: ${tech.get('BB_upper', 'N/A'):.2f}")
        lines.append(f"  布林下轨: ${tech.get('BB_lower', 'N/A'):.2f}")
    lines.append("")
    lines.append("-" * 60)
    lines.append(" 趋势分析:")
    lines.append("-" * 60)
    for period, info in trend_analysis.items():
        lines.append(f"  {period}:")
        for f in info["factors"]:
            lines.append(f"    - {f}")
        lines.append("")
    lines.append("-" * 60)
    lines.append(" 情景推演:")
    lines.append("-" * 60)
    for sc in scenario_results:
        lines.append(f"  {sc['情景']}: {sc['综合评分']} 分 ({sc['信号']})")
    lines.append("")
    lines.append("-" * 60)
    lines.append(" 免责声明:")
    lines.append("  本模型仅用于学习和研究目的，不构成任何投资建议。")
    lines.append("  投资有风险，入市需谨慎。")
    lines.append("=" * 60)
    return "\n".join(lines)

report_text = generate_report_text(scores, details, composite, signal, market_data, macro, tech, trend_analysis)
st.download_button(label="下载完整分析报告 (TXT)", data=report_text, file_name=f"黄金走势分析报告_{datetime.now().strftime('%Y%m%d_%H%M')}.txt", mime="text/plain")

requirements = "streamlit\nyfinance\npandas\nnumpy\nplotly\nrequests\nbeautifulsoup4\n"
with open("requirements.txt", "w") as f:
    f.write(requirements)

print("app.py and requirements.txt generated successfully")
