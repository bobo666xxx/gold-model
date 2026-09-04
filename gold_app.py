import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings("ignore")

# ==========================================
# 页面配置
# ==========================================
st.set_page_config(page_title="黄金多因子趋势分析", layout="wide")

# ==========================================
# 数据获取（全部免费，无需 Key）
# ==========================================
@st.cache_data(ttl=3600)
def fetch_all_data():
    """获取黄金及各因子数据"""
    tickers = {
        "黄金期货": "GC=F",
        "美元指数": "DX-Y.NYB",
        "10年期美债收益率": "^TNX",
        "VIX恐慌指数": "^VIX",
        "原油价格": "CL=F",
        "白银价格": "SI=F",
        "标普500": "^GSPC",
        "美国国债ETF(TLT)": "TLT",
    }

    data = {}
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, period="2y", auto_adjust=True)
            if not df.empty:
                data[name] = df["Close"]
        except:
            pass

    return data


@st.cache_data(ttl=3600)
def build_analysis_df(data):
    """构建因子分析 DataFrame"""
    df = pd.DataFrame(data)
    df = df.dropna()

    # 计算各因子的日收益率
    returns = df.pct_change().dropna()

    # 计算滚动相关系数（60日窗口）
    rolling_corr = {}
    gold_returns = returns["黄金期货"]
    for col in returns.columns:
        if col != "黄金期货":
            rolling_corr[col] = gold_returns.rolling(60).corr(returns[col])

    corr_df = pd.DataFrame(rolling_corr)

    return df, returns, corr_df


# ==========================================
# 多因子综合评分
# ==========================================
def compute_factor_score(returns, lookback=60):
    """
    计算多因子综合评分
    逻辑：
    - 美元指数、美债收益率：与金价负相关 → 它们下跌时利多黄金
    - VIX、原油、白银：与金价正相关 → 它们上涨时利多黄金
    """
    recent = returns.tail(lookback)

    scores = {}

    # 美元指数：下跌利多黄金
    if "美元指数" in recent.columns:
        usd_change = recent["美元指数"].iloc[-1] - recent["美元指数"].iloc[0]
        scores["美元指数"] = -usd_change * 100  # 取反

    # 美债收益率：上升利空黄金
    if "10年期美债收益率" in recent.columns:
        bond_change = recent["10年期美债收益率"].iloc[-1] - recent["10年期美债收益率"].iloc[0]
        scores["10年期美债收益率"] = -bond_change

    # VIX恐慌指数：上升利多黄金（避险）
    if "VIX恐慌指数" in recent.columns:
        vix_change = recent["VIX恐慌指数"].iloc[-1] - recent["VIX恐慌指数"].iloc[0]
        scores["VIX恐慌指数"] = vix_change * 0.5

    # 原油：上涨利多黄金（通胀预期）
    if "原油价格" in recent.columns:
        oil_change = recent["原油价格"].iloc[-1] - recent["原油价格"].iloc[0]
        scores["原油价格"] = oil_change * 0.1

    # 白银：上涨利多黄金（贵金属联动）
    if "白银价格" in recent.columns:
        silver_change = recent["白银价格"].iloc[-1] - recent["白银价格"].iloc[0]
        scores["白银价格"] = silver_change * 0.5

    # 标普500：下跌利多黄金（避险）
    if "标普500" in recent.columns:
        sp_change = recent["标普500"].iloc[-1] - recent["标普500"].iloc[0]
        scores["标普500"] = -sp_change * 0.1

    # 美债ETF(TLT)：上涨利多黄金（利率下行预期）
    if "美国国债ETF(TLT)" in recent.columns:
        tlt_change = recent["美国国债ETF(TLT)"].iloc[-1] - recent["美国国债ETF(TLT)"].iloc[0]
        scores["美国国债ETF(TLT)"] = tlt_change * 2

    return scores


# ==========================================
# 主程序
# ==========================================
st.title("🥇 黄金多因子趋势分析系统")
st.markdown("基于宏观经济因子，量化分析黄金价格趋势方向")

# 获取数据
with st.spinner("正在从 Yahoo Finance 获取数据..."):
    raw_data = fetch_all_data()

if not raw_data:
    st.error("数据获取失败，请稍后刷新重试。")
    st.stop()

df, returns, corr_df = build_analysis_df(raw_data)

# ==========================================
# 侧边栏参数设置
# ==========================================
with st.sidebar:
    st.header("⚙️ 参数设置")
    lookback = st.slider("评分回看窗口（交易日）", 20, 120, 60, step=10)
    corr_window = st.slider("相关性计算窗口（交易日）", 20, 120, 60, step=10)

# ==========================================
# 模块一：黄金价格走势 + 因子对比
# ==========================================
st.header("📈 黄金价格与各因子走势对比")

fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    subplot_titles=("黄金期货价格", "各因子归一化走势"),
                    vertical_spacing=0.08, row_heights=[0.4, 0.6])

# 黄金价格
gold = df["黄金期货"]
fig.add_trace(
    go.Scatter(x=gold.index, y=gold.values, name="黄金",
               line=dict(color="gold", width=2)),
    row=1, col=1
)

# 各因子归一化走势
for col in df.columns:
    if col != "黄金期货":
        normalized = (df[col] - df[col].mean()) / df[col].std()
        fig.add_trace(
            go.Scatter(x=normalized.index, y=normalized.values, name=col,
                       line=dict(width=1), opacity=0.7),
            row=2, col=1
        )

fig.update_layout(height=700, template="plotly_white",
                  legend=dict(orientation="h", y=-0.15))
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 模块二：因子相关性热力图
# ==========================================
st.header("🔗 因子相关性分析")

# 重新计算指定窗口的相关性
gold_ret = returns["黄金期货"]
corr_matrix = {}
for col in returns.columns:
    if col != "黄金期货":
        corr_matrix[col] = gold_ret.rolling(corr_window).corr(returns[col])
corr_matrix_df = pd.DataFrame(corr_matrix)

# 最新相关系数
latest_corr = corr_matrix_df.iloc[-1].sort_values(ascending=False)

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("当前各因子与金价的相关系数")
    corr_display = pd.DataFrame({
        "因子": latest_corr.index,
        "相关系数": latest_corr.values,
        "方向": ["利多 ✅" if v > 0.3 else "利空 ❌" if v < -0.3 else "中性 ➖" for v in latest_corr.values]
    })
    st.dataframe(corr_display, hide_index=True, use_container_width=True)

with col2:
    st.subheader("滚动相关系数变化（近60日窗口）")
    fig_corr = go.Figure()
    for col in corr_matrix_df.columns:
        fig_corr.add_trace(
            go.Scatter(x=corr_matrix_df.index, y=corr_matrix_df[col],
                       name=col, line=dict(width=1.5))
        )
    fig_corr.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_corr.update_layout(height=400, template="plotly_white",
                           yaxis_title="与黄金的相关系数")
    st.plotly_chart(fig_corr, use_container_width=True)

# ==========================================
# 模块三：多因子综合评分与趋势信号
# ==========================================
st.header("📊 多因子综合评分")

scores = compute_factor_score(returns, lookback=lookback)
total_score = sum(scores.values())

# 趋势信号判断
if total_score > 1:
    signal = "🟢 偏多（看涨）"
    signal_color = "green"
elif total_score < -1:
    signal = "🔴 偏空（看跌）"
    signal_color = "red"
else:
    signal = "🟡 震荡（中性）"
    signal_color = "orange"

# 显示核心指标
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("综合因子得分", f"{total_score:.2f}")
with col2:
    st.metric("趋势信号", signal)
with col3:
    latest_gold = df["黄金期货"].iloc[-1]
    gold_change = (df["黄金期货"].iloc[-1] / df["黄金期货"].iloc[-lookback] - 1) * 100
    st.metric("黄金近况", f"${latest_gold:.2f}", f"{gold_change:+.1f}%")

# 各因子贡献度柱状图
st.subheader("各因子贡献度拆解")

factor_names = list(scores.keys())
factor_values = list(scores.values())
colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in factor_values]

fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(
    x=factor_names,
    y=factor_values,
    marker_color=colors,
    text=[f"{v:+.2f}" for v in factor_values],
    textposition="outside"
))
fig_bar.add_hline(y=0, line_dash="dash", line_color="gray")
fig_bar.update_layout(
    height=400,
    template="plotly_white",
    yaxis_title="贡献得分（正=利多，负=利空）",
    title=f"回看 {lookback} 个交易日各因子对黄金的影响"
)
st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# 模块四：综合评分历史走势
# ==========================================
st.header("📉 综合评分历史走势")

# 滚动计算历史评分
rolling_scores = []
for i in range(lookback, len(returns)):
    window_returns = returns.iloc[i - lookback:i]
    s = compute_factor_score(window_returns, lookback=lookback)
    rolling_scores.append(sum(s.values()))

score_series = pd.Series(rolling_scores, index=returns.index[lookback:])

fig_score = go.Figure()
fig_score.add_trace(go.Scatter(
    x=score_series.index, y=score_series.values,
    name="综合评分", fill="tozeroy",
    line=dict(color="gold", width=2),
    fillcolor="rgba(255, 215, 0, 0.1)"
))
fig_score.add_hline(y=0, line_dash="dash", line_color="gray")
fig_score.add_hline(y=1, line_dash="dot", line_color="green", annotation_text="偏多线")
fig_score.add_hline(y=-1, line_dash="dot", line_color="red", annotation_text="偏空线")
fig_score.update_layout(
    height=400, template="plotly_white",
    yaxis_title="综合因子得分",
    title="评分 > 0 偏多 | 评分 < 0 偏空"
)
st.plotly_chart(fig_score, use_container_width=True)

# ==========================================
# 模块五：原始数据查看
# ==========================================
with st.expander("📋 查看原始数据"):
    tab1, tab2 = st.tabs(["各因子收盘价", "各因子日收益率"])
    with tab1:
        st.dataframe(df.tail(30), use_container_width=True)
    with tab2:
        st.dataframe(returns.tail(30), use_container_width=True)

# ==========================================
# 底部说明
# ==========================================
st.divider()
st.markdown("""
**⚠️ 免责声明**：本工具仅供学习和研究使用，不构成任何投资建议。
因子分析基于历史数据的统计关系，过去的相关性不代表未来表现。
数据来源：Yahoo Finance（免费，无需 API Key）。
""")
