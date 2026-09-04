import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings("ignore")

# 设置页面配置
st.set_page_config(page_title="黄金多因子趋势分析系统", layout="wide", page_icon="🥇")

st.title("🥇 黄金多因子趋势分析系统")
st.caption("基于宏观经济因子，量化分析黄金价格趋势方向 | 数据由 yfinance 提供 (若部分数据缺失请检查网络)")

# ==========================================
# 1. 稳健的数据获取函数
# ==========================================
def fetch_single_data(ticker, period="1y"):
    """尝试获取单个资产数据，失败则返回 None"""
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty:
            return None
        # 兼容新版 yfinance 的多级列索引
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        return None

# ==========================================
# 2. 定义因子及获取数据
# ==========================================
st.info("正在同步全球宏观经济数据...")

tickers = {
    "黄金 (XAU)": "GC=F",
    "美元指数 (DXY)": "DX-Y.NYB",
    "10年期美债 (^TNX)": "^TNX",
    "VIX恐慌指数": "^VIX",
    "原油价格 (WTI)": "CL=F",
    "白银价格": "SI=F",
    "标普500指数": "^GSPC"
}

data_frames = {}
for name, ticker in tickers.items():
    data = fetch_single_data(ticker)
    if data is not None:
        # 确保有 Close 列，如果为空则跳过
        if 'Close' in data.columns:
            data_frames[name] = data['Close']
        else:
            # 尝试寻找其他常见的价格列
            if not data.columns.empty:
                data_frames[name] = data.iloc[:, -1]
    else:
        st.warning(f"⚠️ 未能获取 {name} ({ticker}) 的数据，已跳过。")

if not data_frames:
    st.error("❌ 未能获取到任何有效数据，请检查网络或代理设置后刷新重试。")
    st.stop()

st.success(f"数据同步成功，成功加载了 {len(data_frames)} 个有效宏观因子！")

# ==========================================
# 3. 核心数据合并与量化分析 (彻底解决标量错误)
# ==========================================
# 使用 pd.concat 横向合并，自动按索引(日期)对齐，这是最稳健的合并方式
combined_df = pd.concat(data_frames, axis=1)

# 计算日收益率 (pct_change)，用于相关性分析
returns_df = combined_df.pct_change().dropna()

st.markdown("---")
st.subheader("📊 因子相关性热力图 (基于日收益率)")

# 计算相关系数矩阵
corr_matrix = returns_df.corr()

# 绘制热力图
fig_corr = go.Figure(data=go.Heatmap(
    z=corr_matrix.values,
    x=corr_matrix.columns,
    y=corr_matrix.index,
    colorscale='RdYlBu_r',
    zmid=0,
    text=corr_matrix.round(2),
    texttemplate='%{text}',
    textfont={"size":12, "color":"white"}
))
fig_corr.update_layout(height=600, template="plotly_dark")
st.plotly_chart(fig_corr, use_container_width=True)

st.markdown("---")
st.subheader("📈 宏观因子历史价格走势")

# 绘制多因子趋势图
fig_history = make_subplots(rows=2, cols=2, subplot_titles=["黄金 vs 白银", "黄金 vs 美元", "黄金 vs 美债", "黄金 vs VIX"])

if "黄金 (XAU)" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["黄金 (XAU)"], name="黄金", line=dict(color="#FFD700")), row=1, col=1)
if "白银价格" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["白银价格"], name="白银", line=dict(color="#C0C0C0")), row=1, col=1)
    
if "黄金 (XAU)" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["黄金 (XAU)"], name="黄金", line=dict(color="#FFD700")), row=1, col=2)
if "美元指数 (DXY)" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["美元指数 (DXY)"], name="美元", line=dict(color="#3498db")), row=1, col=2)

if "黄金 (XAU)" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["黄金 (XAU)"], name="黄金", line=dict(color="#FFD700")), row=2, col=1)
if "10年期美债 (^TNX)" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["10年期美债 (^TNX)"], name="美债", line=dict(color="#2ecc71")), row=2, col=1)

if "黄金 (XAU)" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["黄金 (XAU)"], name="黄金", line=dict(color="#FFD700")), row=2, col=2)
if "VIX恐慌指数" in combined_df.columns:
    fig_history.add_trace(go.Scatter(x=combined_df.index, y=combined_df["VIX恐慌指数"], name="VIX", line=dict(color="#e74c3c")), row=2, col=2)

fig_history.update_layout(height=800, template="plotly_dark")
st.plotly_chart(fig_history, use_container_width=True)
