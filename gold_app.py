import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="黄金多因子趋势分析系统", layout="wide", page_icon="🥇")

# ==========================================
# 核心数据获取与处理函数
# ==========================================
@st.cache_data(ttl=3600)  # 缓存1小时，避免频繁请求导致API限制
def fetch_and_process_data():
    """统一获取数据并进行对齐处理"""
    tickers = {
        "黄金 (XAU)": "GC=F",
        "美元指数 (DXY)": "DX-Y.NYB",
        "10年期美债 (^TNX)": "^TNX",
        "VIX恐慌指数": "^VIX",
        "原油价格 (WTI)": "CL=F",
        "白银价格": "SI=F",
        "标普500指数": "^GSPC",
        "美债ETF (TLT)": "TLT"
    }
    
    # 获取过去一年的数据
    try:
        df = yf.download(list(tickers.values()), period="1y")
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs("Close", level=1, axis=1)
        else:
            df = df["Close"]
        
        # 统一重命名，方便后续处理
        rename_map = {v: k for k, v in tickers.items()}
        df.rename(columns=rename_map, inplace=True)
        
        # 删除全为空的列（比如某些外汇数据yfinance可能下载不到）
        df.dropna(axis=1, how='all', inplace=True)
        
        # 计算所有因子的日收益率 (pct_change)
        returns_df = df.pct_change().dropna()
        return df, returns_df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        st.warning("请检查网络连接。如果是在本地运行，某些代码可能需要科学上网。")
        return None, None

# ==========================================
# 页面主程序
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; margin-bottom: 0px;'>🥇 黄金多因子趋势分析系统</h1>", unsafe_allow_html=True)
    st.caption("基于宏观经济因子，量化分析黄金价格趋势方向 | 数据由 yfinance 提供")
    st.divider()

    # 1. 获取数据
    prices, returns = fetch_and_process_data()
    
    if prices is None or returns is None:
        return

    # 确保有“黄金”数据才能继续
    if "黄金 (XAU)" not in prices.columns:
        st.error("未能获取到黄金数据，请检查黄金期货代码 `GC=F` 是否可用。")
        return

    # 2. 提取最新数据展示
    latest_prices = prices.iloc[-1]
    daily_returns = returns.iloc[-1]
    
    # 展示最新行情指标
    cols = st.columns(len(latest_prices))
    for i, name in enumerate(latest_prices.index):
        ret_val = daily_returns[name] * 100
        color = "green" if ret_val >= 0 else "red"
        
        with cols[i]:
            st.metric(
                label=name,
                value=f"{latest_prices[name]:,.2f}",
                delta=f"{ret_val:.2f}%"
            )
    
    st.divider()

    # 3. 计算相关性并绘图
    gold_returns = returns["黄金 (XAU)"]
    # 提取除黄金外的其他因子
    factor_returns = returns.drop(columns=["黄金 (XAU)"])
    
    # 计算各因子与黄金的滚动相关性（100天窗口）
    corr_df = pd.DataFrame({
        f"{col} vs 黄金": gold_returns.rolling(window=100).corr(factor_returns[col])
        for col in factor_returns.columns
    }).dropna()

    st.subheader("📊 各宏观因子与黄金价格的滚动相关性分析")
    st.caption("相关性区间：-1 (完全负相关) 到 1 (完全正相关)。趋势线向上代表该因子对金价的正向驱动作用增强。")
    
    fig = make_subplots(specs=[[{"secondary_y": False}]])
    for col in corr_df.columns:
        fig.add_trace(go.Scatter(x=corr_df.index, y=corr_df[col], mode='lines', name=col), secondary_y=False)

    fig.update_layout(
        xaxis_title="时间",
        yaxis_title="相关系数",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=400,
        margin=dict(l=0, r=0, t=0, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 4. 趋势综合评分模型 (简单的量化打分)
    st.subheader("📈 黄金趋势综合评分模型")
    
    # 获取最近 30 天的均值进行打分
    last_30_days_returns = returns.tail(30)
    
    scores = {}
    # 定义正向驱动因子（通常与黄金正相关或同向变动）
    positive_factors = ["10年期美债 (^TNX)", "标普500指数", "美债ETF (TLT)", "原油价格 (WTI)"]
    # 定义负向驱动因子（通常与黄金负相关/对冲）
    negative_factors = ["美元指数 (DXY)", "VIX恐慌指数"] 
    
    # 注意：这里采用简化逻辑，直接根据因子本身的涨跌幅打分
    # 10年期美债/股票跌 -> 黄金可能涨 -> 负分
    # 美元跌 -> 黄金涨 -> 正分
    
    # 为了简化且不出错，我们直接用最近5天和20天的收益率均值来做信号
    signal_data = returns.tail(20).mean()
    
    # 构建综合评分面板
    score_cards = st.columns(3)
    
    with score_cards[0]:
        st.info("**短期情绪指标 (5日)**")
        short_term_signal = returns.tail(5)["黄金 (XAU)"].mean() * 100
        if short_term_signal > 0.5:
            st.success(f"📈 偏多 | 均值涨幅 {short_term_signal:.3f}%")
        elif short_term_signal < -0.5:
            st.error(f"📉 偏空 | 均值跌幅 {abs(short_term_signal):.3f}%")
        else:
            st.warning(f"➖ 震荡 | 均值变动 {short_term_signal:.3f}%")

    with score_cards[1]:
        st.info("**中期趋势指标 (20日)**")
        mid_term_signal = returns.tail(20)["黄金 (XAU)"].mean() * 100
        if mid_term_signal > 0.2:
            st.success(f"📈 偏多 | 均值涨幅 {mid_term_signal:.3f}%")
        elif mid_term_signal < -0.2:
            st.error(f"📉 偏空 | 均值跌幅 {abs(mid_term_signal):.3f}%")
        else:
            st.warning(f"➖ 震荡 | 均值变动 {mid_term_signal:.3f}%")
            
    with score_cards[2]:
        st.info("**宏观环境压力 (综合)**")
        # 综合美元和利率来看
        dxy_change = returns.tail(5)["美元指数 (DXY)"].mean()
        tnx_change = returns.tail(5)["10年期美债 (^TNX)"].mean()
        
        pressure_score = 0
        if dxy_change > 0: pressure_score += 1 # 美元涨
        if tnx_change > 0: pressure_score += 1 # 利率涨
        
        if pressure_score == 0:
            st.success("💰 极度宽松：黄金强力支撑")
        elif pressure_score == 1:
            st.warning("⚖️ 环境一般：多空交织")
        else:
            st.error("🚫 高压环境：黄金承压")

if __name__ == "__main__":
    main()
