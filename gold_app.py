import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="黄金多因子走势分析系统", layout="wide", page_icon="🥇")

st.title("🥇 黄金多因子走势分析系统")
st.caption("基于底层锚定与边际催化模型 | 宏观×地缘×金融×游资 | 量化分析黄金趋势")

# ==========================================
# 2. 数据获取与处理函数
# ==========================================
@st.cache_data(ttl=3600)
def fetch_market_data():
    """
    核心数据获取函数（带完美模拟数据兜底）
    涵盖底层锚定层(美元/实际利率) + 边际催化层(风险/情绪/游资)
    """
    use_mock_data = False
    try:
        # 尝试获取核心黄金数据
        import yfinance as yf
        df_gold = yf.download('GC=F', period='1y', progress=False)
        if df_gold.empty:
            raise Exception("获取黄金数据为空")
            
        data_dict = {}
        tickers = {
            '黄金(GC=F)': 'GC=F',
            '美元指数(DXY)': 'DX-Y.NYB',
            '10年期美债(TNX)': '^TNX',
            '原油(WTI)': 'CL=F',
            '恐慌指数(VIX)': '^VIX'
        }
        
        for name, ticker in tickers.items():
            try:
                df = yf.download(ticker, period='1y', progress=False)
                if not df.empty and name == '黄金(GC=F)':
                    # 黄金保留原始价格
                    data_dict[name] = df['Close']
                elif not df.empty:
                    # 其他指标转为涨跌幅（百分比）进行横向对比
                    data_dict[name] = df['Close'].pct_change() * 100
            except Exception as e:
                print(f"获取 {name} 失败: {e}")
                continue
        
        # 如果获取到的有效数据不足，强制启用模拟数据
        if len(data_dict) < 2:
            raise Exception("有效数据源不足，切换至演示模式")
            
        combined_df = pd.DataFrame(data_dict)
        combined_df.ffill(inplace=True)
        combined_df.dropna(inplace=True)
        
    except Exception as e:
        print(f"网络请求失败: {e}\n正在生成模拟数据...")
        use_mock_data = True
        
        # --- 生成逼真的模拟数据 (兜底机制) ---
        np.random.seed(42)
        dates = pd.date_range(end=datetime.today(), periods=250, freq='B')
        gold_prices = 2600 + np.cumsum(np.random.normal(0, 1.5, len(dates)))
        dxy_rates = np.random.normal(0, 0.1, len(dates))
        tnx_rates = np.random.normal(0, 0.05, len(dates))
        wti_rates = np.random.normal(0, 1.5, len(dates))
        vix_rates = np.random.normal(0, 3, len(dates))
        
        combined_df = pd.DataFrame({
            '黄金(GC=F)': gold_prices,
            '美元指数(DXY)': dxy_rates,
            '10年期美债(TNX)': tnx_rates,
            '原油(WTI)': wti_rates,
            '恐慌指数(VIX)': vix_rates
        }, index=dates)
        # 模拟非商业净多头持仓（游资动向）
        combined_df['游资多头持仓(模拟)'] = np.cumsum(np.random.normal(500, 2000, len(dates)))
        
    return combined_df, use_mock_data

# ==========================================
# 3. 核心逻辑执行与图表渲染
# ==========================================
st.divider()
with st.spinner('正在同步全球宏观经济数据...'):
    combined_df, is_mock = fetch_market_data()

if is_mock:
    st.warning("⚠️ **注意**：当前网络环境无法直接获取国际金融市场实时数据，系统已自动切换为【模拟演示数据】。")
else:
    st.success("✅ 数据同步成功，正在根据底层锚定与边际催化模型进行分析...")

if not combined_df.empty:
    # 顶部数据概览
    latest_data = combined_df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最新黄金价格", f"{latest_data['黄金(GC=F)']:.2f} 美元/盎司")
    if '美元指数(DXY)' in latest_data:
        col2.metric("美元指数变动", f"{latest_data['美元指数(DXY)']:.2f}%", delta=f"{latest_data['美元指数(DXY)']:.2f}%")
    if '恐慌指数(VIX)' in latest_data:
        col3.metric("VIX恐慌指数变动", f"{latest_data['恐慌指数(VIX)']:.2f}%", delta=f"{latest_data['恐慌指数(VIX)']:.2f}%")
    col4.metric("数据时间范围", f"{combined_df.index[0].strftime('%Y-%m-%d')} 至 {combined_df.index[-1].strftime('%Y-%m-%d')}")

    st.divider()
    
    # 核心分析图表
    fig_main = make_subplots(
        rows=2, cols=1, shared_xaxes=True, 
        vertical_spacing=0.03,
        subplot_titles=("📈 黄金价格 vs 美元指数变动", "📊 宏观边际催化因子波动 (涨跌幅%)")
    )

    # 绘制黄金价格
    fig_main.add_trace(
        go.Scatter(x=combined_df.index, y=combined_df['黄金(GC=F)'], name='黄金价格', line=dict(color='#d4af37', width=2)),
        row=1, col=1
    )
    
    # 如果有美元指数则绘制
    if '美元指数(DXY)' in combined_df.columns:
        fig_main.add_trace(
            go.Bar(x=combined_df.index, y=combined_df['美元指数(DXY)'], name='美元指数变动(%)', marker_color='#1f77b4'),
            row=1, col=1
        )
        fig_main.update_layout(yaxis2_title="美元指数变动(%)", yaxis2=dict(side="right"))

    # 绘制其他宏观因子
    catalyst_factors = ['10年期美债(TNX)', '原油(WTI)', '恐慌指数(VIX)']
    colors = ['#ff7f0e', '#2ca02c', '#9467bd']
    for i, factor in enumerate(catalyst_factors):
        if factor in combined_df.columns:
            fig_main.add_trace(
                go.Scatter(x=combined_df.index, y=combined_df[factor], name=factor, line=dict(color=colors[i], width=1)),
                row=2, col=1
            )

    fig_main.update_layout(height=700, xaxis_rangeslider_visible=False, template='plotly_dark')
    st.plotly_chart(fig_main, use_container_width=True)

    # 相关性分析
    st.subheader("🔗 黄金与宏观因子相关性矩阵")
    corr_df = combined_df.corr()
    if '黄金(GC=F)' in corr_df.columns:
        gold_corr = corr_df['黄金(GC=F)'].drop('黄金(GC=F)').sort_values(ascending=False)
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**正相关因子 (同向波动):**")
            for factor, val in gold_corr[gold_corr > 0].items():
                st.metric(factor, f"{val:.2f}")
        with col_b:
            st.markdown("**负相关因子 (反向波动 - 传统避险逻辑):**")
            for factor, val in gold_corr[gold_corr < 0].items():
                st.metric(factor, f"{val:.2f}")
    
    # 游资动向分析
    if '游资多头持仓(模拟)' in combined_df.columns:
        st.divider()
        st.subheader("📉 游资动向：COMEX黄金非商业净多头持仓")
        fig_cot = go.Figure()
        fig_cot.add_trace(go.Scatter(x=combined_df.index, y=combined_df['游资多头持仓(模拟)'], name='净多头持仓', line=dict(color='#e377c2')))
        fig_cot.update_layout(height=400, template='plotly_dark', yaxis_title="持仓量(手)")
        st.plotly_chart(fig_cot, use_container_width=True)

else:
    st.error("系统初始化失败，请稍后重试。")
