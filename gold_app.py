import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
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
@st.cache_data(ttl=3600) # 缓存1小时，避免频繁请求被封IP
def fetch_market_data():
    """
    核心数据获取函数
    涵盖底层锚定层(美元/实际利率) + 边际催化层(风险/情绪/游资)
    """
    data_dict = {}
    tickers = {
        '黄金 (GC=F)': 'GC=F',
        '美元指数 (DX-Y.NYB)': 'DX-Y.NYB',
        '美国10年期国债收益率 (TNX)': '^TNX', # 名义利率代表
        'VIX恐慌指数': '^VIX',
        '原油价格 (CL=F)': 'CL=F',
    }
    
    # 尝试获取数据
    try:
        data = yf.download(list(tickers.values()), period="1y", progress=False)
        # 处理yfinance返回的多级列名问题
        if data.columns.nlevels > 1:
            data.columns = data.columns.get_level_values(0)
            
        for display_name, ticker in tickers.items():
            if ticker in data.columns and not data[ticker].dropna().empty:
                data_dict[display_name] = data[ticker]
                
    except Exception as e:
        st.warning(f"⚠️ 数据请求异常：{e}，正在尝试使用备用方式...")
        for display_name, ticker in tickers.items():
            try:
                df = yf.download(ticker, period="1y", progress=False)
                if not df.empty:
                    data_dict[display_name] = df['Close']
            except:
                pass
                
    return data_dict

# ==========================================
# 3. 主程序逻辑
# ==========================================

# 加载数据
with st.spinner('📡 正在同步全球宏观与游资情绪数据...'):
    market_data = fetch_market_data()

if not market_data:
    st.error("❌ 无法获取市场数据！请检查网络环境（如是否需要科学上网）后刷新页面。")
else:
    st.success(f"✅ 数据同步成功！成功加载 {len(market_data)} 个核心监测因子。")
    
    # 合并数据为统一DataFrame以便分析
    combined_df = pd.DataFrame(market_data)
    combined_df.ffill() # 前向填充，解决不同资产交易日差异导致的空值
    
    st.divider()
    
    # --- 展示核心指标看板 ---
    st.subheader("📊 核心因子实时监测面板")
    cols = st.columns(len(market_data))
    for i, col in enumerate(cols):
        name = list(market_data.keys())[i]
        latest_val = market_data[name].iloc[-1]
        change_pct = ((latest_val / market_data[name].iloc[-2]) - 1) * 100
        arrow = "🔺" if change_pct >= 0 else "🔻"
        color = "red" if change_pct >= 0 else "green"
        
        col.metric(
            label=name,
            value=f"{latest_val:,.2f}" if '美元' not in name else f"{latest_val:,.2f} %",
            delta=f"{arrow} {abs(change_pct):.2f}%",
            delta_color=color
        )

    st.divider()

    # --- 展示综合走势图 ---
    st.subheader("📈 黄金走势与宏观因子联动分析图")
    
    if '黄金 (GC=F)' in combined_df.columns:
        # 创建带副图的画布
        fig = make_subplots(
            specs=[[{"secondary_y": True}]], # 修正之前的语法错误，设置双Y轴
            subplot_titles=["黄金价格 vs 美元指数 / VIX恐慌指数"]
        )
        
        # 绘制主图：黄金价格
        fig.add_trace(
            go.Scatter(x=combined_df.index, y=combined_df['黄金 (GC=F)'], name='黄金价格', line=dict(color='#DAA520', width=3)),
            secondary_y=False
        )
        
        # 绘制副图1：美元指数 (反向指标)
        if '美元指数 (DX-Y.NYB)' in combined_df.columns:
            fig.add_trace(
                go.Scatter(x=combined_df.index, y=combined_df['美元指数 (DX-Y.NYB)'], name='美元指数', line=dict(color='blue', width=1.5, dash='dot')),
                secondary_y=True
            )
            
        # 绘制副图2：VIX恐慌指数 (避险情绪)
        if 'VIX恐慌指数' in combined_df.columns:
            fig.add_trace(
                go.Scatter(x=combined_df.index, y=combined_df['VIX恐慌指数'], name='VIX恐慌指数', line=dict(color='red', width=1.5, dash='dash')),
                secondary_y=True
            )

        # 设置图表布局
        fig.update_layout(
            height=600,
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_title="时间"
        )
        
        fig.update_yaxes(title_text="黄金价格 (美元/盎司)", secondary_y=False)
        fig.update_yaxes(title_text="指数数值 (右侧坐标)", secondary_y=True)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 简单的量化结论输出
        st.info("""
        💡 **模型分析结论参考：**
        *   **底层锚定**：观察黄金与美元指数的走势是否呈现明显的“剪刀差”（负相关）。若美元走弱而黄金走强，说明底层信用逻辑支撑金价。
        *   **边际催化**：观察 VIX 指数或原油价格是否出现急剧拉升。若 VIX 飙升伴随金价突破，说明有地缘政治或金融恐慌资金（游资/避险盘）正在短期涌入。
        *   **注意**：部分海外金融数据（如美债实际利率）因接口限制可能缺失，当前已使用10年期名义利率作为近似替代。
        """)
    else:
        st.warning("未能获取黄金主数据，无法绘制趋势图。")
