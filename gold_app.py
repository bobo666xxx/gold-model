import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="黄金多因子趋势分析系统", layout="wide", page_icon="🥇")

st.title("🥇 黄金多因子趋势分析系统")
st.markdown("基于宏观经济因子，量化分析黄金价格趋势方向 | 数据由 yfinance 提供")

# ==========================================
# 核心数据获取与处理函数 (已优化防御逻辑)
# ==========================================
@st.cache_data(ttl=7200)
def fetch_and_process_data():
    """统一获取数据并进行对齐处理，包含强大的容错机制"""
    tickers = {
        "黄金 (XAU)": "GC=F",
        "美元指数 (DXY)": "DX-Y.NYB",
        "10年期美债 (^TNX)": "^TNX",
        "VIX恐慌指数": "^VIX",
        "原油价格 (WTI)": "CL=F",
        "白银价格": "SI=F",
        "标普500指数": "^GSPC"
    }

    dfs = {}
    errors = []

    # 循环获取每个指标，如果失败只跳过该指标，不导致整个程序崩溃
    for name, symbol in tickers.items():
        try:
            df = yf.download(symbol, period="1y", progress=False)
            if df.empty:
                errors.append(f"{name} 未获取到数据")
            else:
                dfs[name] = df[['Close']] # 只保留收盘价
        except Exception as e:
            errors.append(f"{name} 获取异常: {str(e)}")

    if not errors:
        errors = None

    return dfs, errors


# ==========================================
# 主程序逻辑
# ==========================================
with st.spinner("正在从全球金融市场获取实时数据..."):
    data_dict, fetch_errors = fetch_and_process_data()

if not data_dict:
    st.error("❌ 无法获取任何数据，请检查网络连接，确保已开启代理。")
    st.warning("请检查网络连接。如果是在本地运行，某些代码可能需要科学上网。")
    st.stop() # 停止运行，防止后续报错

# 如果有部分指标获取失败，给出温和的提示，但不打断程序
if fetch_errors:
    st.warning("⚠️ 网络存在波动，以下指标暂时无法加载，分析将基于其他可用因子进行：")
    for err in fetch_errors:
        st.text(f"   - {err}")

# 获取黄金数据用于计算收益率和相关性
gold_df = data_dict.get("黄金 (XAU)")

# 合并所有因子的收盘价，用于计算相关性矩阵
if "黄金 (XAU)" in data_dict:
    combined_df = pd.DataFrame({name: df['Close'] for name, df in data_dict.items()})
    
    # 计算各因子的日收益率
    daily_returns = combined_df.pct_change().dropna()

    # 计算相关性矩阵
    corr_matrix = daily_returns.corr()

    # ==========================================
    # 界面展示模块
    # ==========================================
    st.markdown("---")
    
    # 1. 黄金价格走势
    st.subheader("1. 黄金价格走势 (近1年)")
    fig_gold = go.Figure()
    fig_gold.add_trace(go.Scatter(x=gold_df.index, y=gold_df['Close'], mode='lines', name='黄金价格', line=dict(color='gold', width=3)))
    fig_gold.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_gold, use_container_width=True)

    st.markdown("---")

    # 2. 相关性热力图
    st.subheader("2. 宏观经济因子与黄金的相关性热力图")
    fig_corr = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns,
        y=corr_matrix.index,
        zmid=0,
        colorscale='RdBu_r',
        text=corr_matrix.round(2).astype(str),
        texttemplate="%{text}",
    ))
    fig_corr.update_layout(height=500, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_corr, use_container_width=True)

    st.markdown("---")

    # 3. 因子综合评分 (简单加权示例)
    st.subheader("3. 近期因子趋势评分 (仅供参考)")
    
    # 计算最近30天的平均收益率，作为近期趋势的量化指标
    recent_returns = daily_returns.tail(30).mean()
    
    # 简单的评分逻辑：
    # 黄金 vs 美元/美债(负相关)：如果它们涨，说明持有黄金的成本变高，黄金趋势评分-1
    # 黄金 vs VIX/原油(正相关)：如果它们涨，说明避险/通胀情绪升温，黄金趋势评分+1
    correlation_guide = {
        "美元指数 (DXY)": -1,
        "10年期美债 (^TNX)": -1,
        "VIX恐慌指数": 1,
        "原油价格 (WTI)": 1,
        "标普500指数": -1
    }

    scores = []
    for name, direction in correlation_guide.items():
        if name in recent_returns.index:
            # 结合收益率正负和相关性方向得出当前趋势评分
            score = direction * recent_returns[name] * 100
            scores.append({"因子": name, "近期趋势评分": round(score, 2)})

    if scores:
        score_df = pd.DataFrame(scores)
        # 使用颜色标记正负趋势
        st.dataframe(score_df.style.applymap(
            lambda v: 'color: green' if v > 0 else 'color: red', 
            subset=['近期趋势评分']
        ), use_container_width=True)
        st.caption("*评分基于过去30天数据计算，正值表示该因子当前状态支持黄金上涨，负值表示压制黄金。*")

else:
    st.error("未能成功获取黄金(XAU)的核心数据，无法进行相关性计算。")
