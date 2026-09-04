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
        if df.empty or 'Close' not in df.columns:
            return None
        return df[['Close']]
    except Exception as e:
        return None

def fetch_all_data():
    """并行获取所有因子数据"""
    tickers = {
        "黄金 (XAU/USD)": "GC=F",
        "美元指数 (DXY)": "DX-Y.NYB",
        "10年期美债收益率 (^TNX)": "^TNX",
        "VIX 恐慌指数": "^VIX",
        "WTI 原油价格": "CL=F",
        "白银价格": "SI=F",
        "标普500指数": "^GSPC"
    }
    
    data_dict = {}
    # 创建一个进度条，提升用户体验
    progress_bar = st.progress(0)
    total = len(tickers)
    
    for i, (name, ticker) in enumerate(tickers.items()):
        df = fetch_single_data(ticker)
        if df is not None:
            data_dict[name] = df['Close']
        # 更新进度条
        progress_bar.progress((i + 1) / total)
    
    return data_dict

# ==========================================
# 2. 主程序运行区域
# ==========================================

# 尝试获取数据
st.markdown("### 📡 正在同步全球宏观经济数据...")
raw_data = fetch_all_data()

# 终极防御：如果没有拿到任何有效数据，直接友好提示并停止
if not raw_data:
    st.error("⚠️ 数据获取失败：未能从网络获取到任何有效的因子数据。")
    st.warning("💡 解决方案：如果您在本地运行，请检查网络连接（或确保科学上网工具处于全局模式），然后**彻底重启终端**并再次运行 streamlit 命令。")
    st.stop()

st.success(f"✅ 数据同步成功，成功加载了 {len(raw_data)} 个有效宏观因子！")

# ==========================================
# 3. 数据清洗与对齐 (彻底解决合并报错的核心)
# ==========================================
# 将获取到的 Series 字典，通过列合并(axis=1)组成一个大 DataFrame
combined_df = pd.DataFrame(raw_data)

# 删除没有任何数据的行
combined_df.dropna(how='all', inplace=True)
# 用前一个有效值填充缺失值（解决不同资产收盘时间戳微小差异）
combined_df.ffill(inplace=True)

# ==========================================
# 4. 量化指标计算与展示
# ==========================================
st.markdown("---")
st.markdown("### 📊 核心量化指标分析")

# 提取黄金数据，用于计算基准指标
gold_series = combined_df['黄金 (XAU/USD)']
dxy_series = combined_df['美元指数 (DXY)'] if '美元指数 (DXY)' in combined_df else None

# 1. 当前金价与30日均线
gold_ma30 = gold_series.rolling(window=30).mean()
current_price = gold_series.iloc[-1]
ma30_price = gold_ma30.iloc[-1]
deviation = (current_price - ma30_price) / ma30_price * 100
deviation_color = "red" if deviation >= 0 else "green"
trend_direction = "强势突破" if deviation >= 0 else "弱势回调"

# 2. 黄金与美元相关系数
if dxy_series is not None:
    correlation = gold_series.corr(dxy_series)
else:
    correlation = "数据缺失"

# 使用 st.columns 布局展示指标卡片
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("当前黄金价格 (COMEX)", f"${current_price:,.2f}", f"{deviation:+.2f}%", help="较30日均线偏离度")
    st.caption(f"当前趋势: {trend_direction} 📈" if deviation >= 0 else f"当前趋势: {trend_direction} 📉")
with col2:
    st.metric("30日均线价格", f"${ma30_price:,.2f}")
with col3:
    st.metric("黄金与美元相关系数", f"{correlation:.4f}" if isinstance(correlation, float) else correlation, help="负相关越高，说明黄金避险属性越强")
with col4:
    # 简单计算近5日动能
    mom_5 = gold_series.iloc[-1] - gold_series.iloc[-5]
    st.metric("近5日价格动能", f"${mom_5:+.2f}", help="反映短期市场情绪")

# ==========================================
# 5. 交互式可视化图表
# ==========================================
st.markdown("---")
st.markdown("### 📈 黄金与宏观因子联动走势")

# 创建子图
fig = make_subplots(
    specs=[[{"secondary_y": True}]],
    shared_xaxes=True,
    vertical_spacing=0.03,
    subplot_titles=("黄金价格联动宏观因子走势分析",)
)

# 添加黄金主图
fig.add_trace(
    go.Scatter(x=combined_df.index, y=combined_df['黄金 (XAU/USD)'], name="黄金 (左轴)", line=dict(width=2, color='#d4af37')),
    secondary_y=False,
)

# 添加其他因子（统一进行归一化处理，方便对比走势）
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#9467bd', '#8c564b']
color_idx = 0

for name in combined_df.columns:
    if name != '黄金 (XAU/USD)':
        # 归一化：(当前值 - 起始值) / 起始值 * 100
        base_value = combined_df[name].iloc[0]
        if base_value != 0:
            normalized_series = (combined_df[name] / base_value - 1) * 100
            
            fig.add_trace(
                go.Scatter(
                    x=combined_df.index, 
                    y=normalized_series, 
                    name=name,
                    line=dict(width=1.5, color=colors[color_idx % len(colors)]),
                    hovertemplate='%{x|%Y-%m-%d}: %{y:.2f}%<extra></extra>'
                ),
                secondary_y=True,
            )
            color_idx += 1

# 图表布局优化
fig.update_layout(
    height=600,
    margin=dict(l=20, r=20, t=40, b=20),
    hovermode='x unified',
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    ),
    showlegend=True
)

fig.update_yaxes(title_text="黄金价格 (美元/盎司)", secondary_y=False)
fig.update_yaxes(title_text="其他因子涨跌幅 (%)", secondary_y=True)

# 渲染图表
st.plotly_chart(fig, use_container_width=True)

st.info("💡 解读指南：右轴为归一化后的涨跌幅。当黄金上涨而其他因子下跌（或负相关因子背离）时，通常代表强烈的独立避险行情。")
