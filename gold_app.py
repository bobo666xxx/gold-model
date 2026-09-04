
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="黄金走势多因子分析模型",
    page_icon="\u2605",
    layout="wide"
)

st.title("\u2605 黄金走势多因子分析模型")
st.caption("数据来源: Yahoo Finance / FRED (全部免费, 无需 API Key)")
st.caption(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ============================================================
# 数据获取模块（全部免费，无需 API Key）
# ============================================================

@st.cache_data(ttl=300)
def fetch_market_data():
    """从 Yahoo Finance 获取市场数据"""
    try:
        tickers = {
            "gold": "GC=F",
            "dxy": "DX-Y.NYB",
            "us10y": "TMUS10Y",
            "vix": "VIXY",
            "silver": "SI=F",
            "oil": "CL=F",
            "btc": "BTC-USD",
        }
        data = {}
        for name, ticker in tickers.items():
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="6mo")
                if not hist.empty:
                    data[name] = hist
            except Exception:
                continue
        return data
    except Exception as e:
        st.error(f"市场数据获取异常: {e}")
        return {}


@st.cache_data(ttl=300)
def fetch_fred_data(series_id):
    """从 FRED 获取数据（无需 Key）"""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_all_macro_data():
    """批量获取所有宏观数据"""
    series = {
        "cpi": "CPIAUCSL",
        "unemp": "UNRATE",
        "fed_rate": "FEDFUNDS",
        "nfp": "PAYEMS",
        "retail": "RSXFSN",
        "indprod": "INDPRO",
        "debt": "GFDEBTN",
    }
    result = {}
    for key, sid in series.items():
        df = fetch_fred_data(sid)
        if not df.empty:
            result[key] = df
    return result


# ============================================================
# 多因子评分引擎
# ============================================================

def calculate_factor_scores(market_data, macro):
    """计算各因子对黄金的评分（-100 到 +100，正=利多，负=利空）"""
    scores = {}
    details = {}

    # 1. 美元指数因子（负相关）
    if "dxy" in market_data and len(market_data["dxy"]) > 20:
        dxy = market_data["dxy"]["Close"]
        dxy_cur = dxy.iloc[-1]
        dxy_1m = (dxy.iloc[-1] / dxy.iloc[-22] - 1) * 100 if len(dxy) > 22 else 0
        dxy_3m = (dxy.iloc[-1] / dxy.iloc[-66] - 1) * 100 if len(dxy) > 66 else 0
        score = np.clip(-dxy_1m * 15, -100, 100)
        scores["美元指数"] = score
        details["美元指数"] = f"当前: {dxy_cur:.2f} | 1月变动: {dxy_1m:+.2f}% | 3月变动: {dxy_3m:+.2f}%"
    else:
        scores["美元指数"] = 0
        details["美元指数"] = "数据不可用"

    # 2. 实际利率因子（负相关）
    if "us10y" in market_data and "cpi" in macro:
        us10y = market_data["us10y"]["Close"].iloc[-1]
        cpi_yoy = macro["cpi"]["CPIAUCSL"].pct_change(12).dropna()
        cpi_val = cpi_yoy.iloc[-1] if not cpi_yoy.empty else 3.0
        real_rate = us10y - cpi_val
        if real_rate < 0:
            score = np.clip(abs(real_rate) * 20, 0, 100)
        else:
            score = np.clip(-real_rate * 15, -100, 0)
        scores["实际利率"] = score
        details["实际利率"] = f"10Y国债: {us10y:.2f}% | CPI同比: {cpi_val:.2f}% | 实际利率: {real_rate:.2f}%"
    else:
        scores["实际利率"] = 0
        details["实际利率"] = "数据不可用"

    # 3. 通胀因子（正相关）
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

    # 4. 就业数据因子（非农低于预期利多黄金）
    if "nfp" in macro and len(macro["nfp"]) > 2:
        nfp = macro["nfp"]["PAYEMS"].diff()
        nfp = nfp.dropna()
        if not nfp.empty:
            latest = nfp.iloc[-1]
            avg = nfp.iloc[-12:].mean() if len(nfp) >= 12 else nfp.mean()
            dev = latest - avg
            score = np.clip(-dev / 50, -100, 100)
            scores["就业数据"] = score
            details["就业数据"] = f"最新非农: {latest:+.0f}K | 12月均值: {avg:+.0f}K | 偏差: {dev:+.0f}K"
        else:
            scores["就业数据"] = 0
            details["就业数据"] = "数据不足"
    else:
        scores["就业数据"] = 0
        details["就业数据"] = "数据不可用"

    # 5. 失业率因子
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
        details["失业率"] = "数据不可用"

    # 6. 美联储利率因子
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
        details["美联储利率"] = "数据不可用"

    # 7. 消费指数因子
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
        details["消费指数"] = "数据不可用"

    # 8. 工业生产指数因子
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
        details["生产指数"] = "数据不可用"

    # 9. VIX恐慌指数因子（避险）
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

    # 10. 央行购金/避险需求（金银比代理）
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

    # 11. 美国负债因子
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
        details["美国负债"] = "数据不可用"

    return scores, details


def calculate_composite_score(scores):
    """计算加权综合评分"""
    weights = {
        "美元指数": 0.15,
        "实际利率": 0.18,
        "通胀数据": 0.12,
        "就业数据": 0.10,
        "失业率": 0.08,
        "美联储利率": 0.12,
        "消费指数": 0.05,
        "生产指数": 0.05,
        "地缘/避险(VIX)": 0.05,
        "央行购金/避险": 0.05,
        "美国负债": 0.05,
    }
    total_weight = 0
    weighted_sum = 0
    for factor, score in scores.items():
        w = weights.get(factor, 0.05)
        weighted_sum += score * w
        total_weight += w
    return weighted_sum / total_weight if total_weight > 0 else 0


def get_signal(composite):
    """根据综合评分给出信号"""
    if composite > 50:
        return "强烈看多", "\u2705"
    elif composite > 20:
        return "偏多", "\U0001F7E2"
    elif composite > -20:
        return "中性震荡", "\U0001F7E1"
    elif composite > -50:
        return "偏空", "\U0001F7E0"
    else:
        return "强烈看空", "\U0001F534"


# ============================================================
# 主界面
# ============================================================

with st.spinner("正在获取数据并计算评分..."):
    market_data = fetch_market_data()
    macro = fetch_all_macro_data()

if not market_data:
    st.error("所有市场数据获取失败，请检查网络连接。")
    st.stop()

scores, details = calculate_factor_scores(market_data, macro)
composite = calculate_composite_score(scores)
signal, signal_icon = get_signal(composite)

# ---- 顶部概览 ----
col1, col2, col3, col4 = st.columns(4)

# 金价
if "gold" in market_data:
    gold_price = market_data["gold"]["Close"].iloc[-1]
    gold_chg = (market_data["gold"]["Close"].iloc[-1] / market_data["gold"]["Close"].iloc[-2] - 1) * 100
    col1.metric("黄金价格", f"${gold_price:.2f}", f"{gold_chg:+.2f}%")
else:
    col1.metric("黄金价格", "N/A", "")

# 综合评分
col2.metric("综合评分", f"{composite:+.1f} / 100", "")

# 信号
col3.text(f"趋势信号\n{signal_icon} {signal}")

# 美元指数
if "dxy" in market_data:
    dxy_val = market_data["dxy"]["Close"].iloc[-1]
    col4.metric("美元指数", f"{dxy_val:.2f}", "")

st.divider()

# ---- 因子评分表 ----
st.subheader("各因子评分明细")

factor_names = list(scores.keys())
factor_values = list(scores.values())
factor_details = [details.get(f, "") for f in factor_names]

def factor_color(s):
    if s > 30:
        return "\u2705"
    elif s > 0:
        return "\U0001F7E2"
    elif s > -30:
        return "\U0001F7E1"
    else:
        return "\U0001F534"

table_data = []
for i, name in enumerate(factor_names):
    table_data.append({
        "因子": name,
        "评分": f"{factor_values[i]:+.1f}",
        "信号": factor_color(factor_values[i]),
        "详情": factor_details[i],
    })

df_table = pd.DataFrame(table_data)
st.table(df_table)

# ---- 雷达图 ----
st.subheader("因子雷达图")

categories = factor_names
values = factor_values + [factor_values[0]]

fig_radar = go.Figure()
fig_radar.add_trace(go.Scatterpolar(
    r=values,
    theta=categories,
    fill='toself',
    fillcolor='rgba(255, 165, 0, 0.3)',
    line_color='orange',
    name='当前评分'
))
fig_radar.add_trace(go.Scatterpolar(
    r=[0]*len(categories),
    theta=categories,
    fill='toself',
    fillcolor='rgba(0, 128, 255, 0.1)',
    line_color='blue',
    name='中性基准'
))

fig_radar.update_layout(
    polar=dict(
        radialaxis=dict(range=[-100, 100], tickfont=dict(size=10)),
        angularaxis=dict(tickfont=dict(size=10))
    ),
    height=550,
    width=700,
)
st.plotly_chart(fig_radar, use_container_width=True)

# ---- 各因子得分柱状图 ----
st.subheader("各因子得分对比")

colors_bar = ["#2E7D32" if v > 0 else "#C62828" for v in factor_values]
fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(
    x=factor_names,
    y=factor_values,
    marker_color=colors_bar,
    text=[f"{v:+.1f}" for v in factor_values],
    textposition='auto',
))
fig_bar.update_layout(
    xaxis_tickangle=-45,
    yaxis_title="评分",
    yaxis_range=[-100, 100],
    height=400,
)
st.plotly_chart(fig_bar, use_container_width=True)

# ---- 金价走势 ----
st.subheader("金价走势（近6个月）")

if "gold" in market_data:
    fig_gold = go.Figure()
    fig_gold.add_trace(go.Candlestick(
        x=market_data["gold"].index,
        open=market_data["gold"]["Open"],
        high=market_data["gold"]["High"],
        low=market_data["gold"]["Low"],
        close=market_data["gold"]["Close"],
        name="金价"
    ))
    fig_gold.update_layout(height=400, xaxis_title="日期", yaxis_title="美元/盎司")
    st.plotly_chart(fig_gold, use_container_width=True)

# ---- 美元指数走势 ----
if "dxy" in market_data:
    st.subheader("美元指数走势（近6个月）")
    fig_dxy = go.Figure()
    fig_dxy.add_trace(go.Scatter(
        x=market_data["dxy"].index,
        y=market_data["dxy"]["Close"],
        line_color="#1565C0",
        name="美元指数"
    ))
    fig_dxy.update_layout(height=350, xaxis_title="日期", yaxis_title="美元指数")
    st.plotly_chart(fig_dxy, use_container_width=True)

# ---- 实际利率走势 ----
if "us10y" in market_data and "cpi" in macro:
    st.subheader("10年期国债收益率 vs CPI同比")
    fig_real = go.Figure()
    us10y_series = market_data["us10y"]["Close"]
    cpi_yoy = macro["cpi"]["CPIAUCSL"].pct_change(12)

    common_idx = us10y_series.index.intersection(cpi_yoy.dropna().index)
    if len(common_idx) > 0:
        fig_real.add_trace(go.Scatter(
            x=common_idx,
            y=us10y_series[common_idx],
            line_color="#E65100",
            name="10Y国债收益率"
        ))
        fig_real.add_trace(go.Scatter(
            x=common_idx,
            y=cpi_yoy[common_idx],
            line_color="#1B5E20",
            name="CPI同比"
        ))
        fig_real.update_layout(height=350, xaxis_title="日期", yaxis_title="%")
        st.plotly_chart(fig_real, use_container_width=True)

# ---- 情景推演 ----
st.subheader("情景推演")

scenarios = [
    {
        "name": "美联储降息周期开启",
        "美元指数": -30, "实际利率": 40, "通胀数据": 0,
        "就业数据": 20, "失业率": 0, "美联储利率": 50,
        "消费指数": 10, "生产指数": 10, "地缘/避险(VIX)": 0,
        "央行购金/避险": 0, "美国负债": 10,
    },
    {
        "name": "美国经济衰退",
        "美元指数": -20, "实际利率": -30, "通胀数据": -40,
        "就业数据": -50, "失业率": 0, "美联储利率": 40,
        "消费指数": -40, "生产指数": -40, "地缘/避险(VIX)": 40,
        "央行购金/避险": 20, "美国负债": 20,
    },
    {
        "name": "地缘政治危机升级",
        "美元指数": 10, "实际利率": 0, "通胀数据": 30,
        "就业数据": 0, "失业率": 0, "美联储利率": 0,
        "消费指数": -20, "生产指数": -20, "地缘/避险(VIX)": 60,
        "央行购金/避险": 40, "美国负债": 10,
    },
    {
        "name": "美国经济软着陆",
        "美元指数": 20, "实际利率": 20, "通胀数据": 10,
        "就业数据": 10, "失业率": 0, "美联储利率": 0,
        "消费指数": 20, "生产指数": 20, "地缘/避险(VIX)": -20,
        "央行购金/避险": -10, "美国负债": 10,
    },
]

weights = {
    "美元指数": 0.15, "实际利率": 0.18, "通胀数据": 0.12,
    "就业数据": 0.10, "失业率": 0.08, "美联储利率": 0.12,
    "消费指数": 0.05, "生产指数": 0.05, "地缘/避险(VIX)": 0.05,
    "央行购金/避险": 0.05, "美国负债": 0.05,
}

scenario_results = []
for sc in scenarios:
    total_w = 0
    weighted = 0
    for k, v in sc.items():
        if k == "name":
            continue
        w = weights.get(k, 0.05)
        weighted += v * w
        total_w += w
    sc_score = weighted / total_w if total_w > 0 else 0
    sc_signal, _ = get_signal(sc_score)
    scenario_results.append({
        "情景": sc["name"],
        "综合评分": f"{sc_score:+.1f}",
        "信号": sc_signal,
    })

df_scenario = pd.DataFrame(scenario_results)
st.table(df_scenario)

# ---- 免责声明 ----
st.divider()
st.caption(
    "免责声明: 本模型仅用于学习和研究目的，不构成任何投资建议。"
    "数据来源于公开免费接口，可能存在延迟或误差。"
    "投资有风险，入市需谨慎。"
)

# ============================================================
# 下载分析报告
# ============================================================

def generate_report_text(scores, details, composite, signal, market_data, macro):
    """生成完整的分析报告文本"""
    lines = []
    lines.append("=" * 60)
    lines.append(" 黄金走势多因子分析报告")
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
        marker = "\u2705" if score > 30 else ("\U0001F7E2" if score > 0 else ("\U0001F7E1" if score > -30 else "\U0001F534"))
        detail = details.get(factor, "")
        lines.append(f"  {i}. {marker} {factor}: {score:+.1f} 分")
        lines.append(f"     详情: {detail}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(" 综合分析:")
    lines.append("-" * 60)

    bull_factors = [f for f, s in scores.items() if s > 10]
    bear_factors = [f for f, s in scores.items() if s < -10]

    if bull_factors:
        lines.append(f"  利多因素: {', '.join(bull_factors)}")
    else:
        lines.append("  利多因素: 无明显利多")

    if bear_factors:
        lines.append(f"  利空因素: {', '.join(bear_factors)}")
    else:
        lines.append("  利空因素: 无明显利空")

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


report_text = generate_report_text(scores, details, composite, signal, market_data, macro)

st.download_button(
    label="下载完整分析报告 (TXT)",
    data=report_text,
    file_name=f"黄金走势分析报告_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
    mime="text/plain",
)

# ============================================================
# requirements.txt 内容
# ============================================================
requirements = """streamlit
yfinance
pandas
numpy
plotly
"""

with open("requirements.txt", "w") as f:
    f.write(requirements)

print("app.py and requirements.txt generated successfully")
