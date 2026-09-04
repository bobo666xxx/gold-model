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
# 页面配置
# ==========================================
st.set_page_config(page_title="黄金多因子走势分析系统", layout="wide", page_icon="")

st.title(" 黄金多因子走势分析系统")
st.caption("基于双层四因子定价模型 | 宏观经济 × 地缘政治 × 金融情绪 × 游资动向")

# ==========================================
# 1. 数据获取模块
# ==========================================
@st.cache_data(ttl=7200)
def fetch_market_data():
    """获取所有市场数据"""
    tickers = {
        "黄金": "GC=F",
        "美元指数": "DX-Y.NYB",
        "10年期美债": "^TNX",
        "2年期美债": "^IRX",
        "VIX恐慌指数": "^VIX",
        "原油WTI": "CL=F",
        "白银": "SI=F",
        "标普500": "^GSPC",
        "比特币": "BTC-USD",
    }
    
    data = {}
    errors = []
    
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, period="2y", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[name] = df['Close']
            else:
                errors.append(name)
        except:
            errors.append(name)
    
    return data, errors

# ==========================================
# 2. 因子计算引擎
# ==========================================
def calculate_factors(data):
    """计算各维度因子得分"""
    factors = {}
    
    # --- 因子1: 美元信用因子 (反向指标，美元越弱黄金越强) ---
    if "美元指数" in data:
        dxy = data["美元指数"]
        # 归一化到0-100，然后取反
        dxy_norm = (dxy - dxy.min()) / (dxy.max() - dxy.min()) * 100
        factors["美元信用因子"] = 100 - dxy_norm  # 反转：美元弱=利好黄金
    
    # --- 因子2: 实际利率因子 (反向指标) ---
    if "10年期美债" in data and "2年期美债" in data:
        spread = data["10年期美债"] - data["2年期美债"]  # 期限利差
        spread_norm = (spread - spread.min()) / (spread.max() - spread.min()) * 100
        factors["实际利率因子"] = 100 - spread_norm  # 利差收窄=利好黄金
    
    # --- 因子3: 金融情绪因子 (VIX越高=恐慌越大=利好黄金) ---
    if "VIX恐慌指数" in data:
        vix = data["VIX恐慌指数"]
        vix_norm = (vix - vix.min()) / (vix.max() - vix.min()) * 100
        factors["金融情绪因子"] = vix_norm
    
    # --- 因子4: 通胀预期因子 (原油上涨=通胀预期升温=利好黄金) ---
    if "原油WTI" in data:
        oil = data["原油WTI"]
        oil_ma20 = oil.rolling(20).mean()
        oil_deviation = (oil - oil_ma20) / oil_ma20 * 100
        oil_norm = (oil_deviation - oil_deviation.min()) / (oil_deviation.max() - oil_deviation.min()) * 100
        factors["通胀预期因子"] = oil_norm
    
    # --- 因子5: 游资动向因子 (用比特币作为投机资金代理) ---
    if "比特币" in data:
        btc = data["比特币"]
        btc_momentum = btc.pct_change(5) * 100  # 5日动量
        btc_norm = (btc_momentum - btc_momentum.min()) / (btc_momentum.max() - btc_momentum.min()) * 100
        factors["游资动向因子"] = btc_norm
    
    # --- 因子6: 避险需求因子 (标普下跌=风险偏好下降=利好黄金) ---
    if "标普500" in data:
        spx = data["标普500"]
        spx_return = spx.pct_change(10) * 100
        spx_norm = (spx_return - spx_return.min()) / (spx_return.max() - spx_return.min()) * 100
        factors["避险需求因子"] = 100 - spx_norm  # 股市跌=避险升
    
    return factors

def calculate_composite_score(factors):
    """
    计算黄金综合预测指数 (GPI - Gold Predict Index)
    基于双层四因子模型权重分配
    """
    # 底层锚定层权重 45%，边际催化层权重 55%
    weights = {
        "美元信用因子": 0.25,   # 底层锚定
        "实际利率因子": 0.20,   # 底层锚定
        "金融情绪因子": 0.15,   # 边际催化
        "通胀预期因子": 0.15,   # 边际催化
        "游资动向因子": 0.10,   # 边际催化
        "避险需求因子": 0.15,   # 边际催化
    }
    
    composite = pd.Series(0.0, index=list(factors.values())[0].index)
    
    for name, weight in weights.items():
        if name in factors:
            aligned = factors[name].reindex(composite.index).ffill().bfill()
            composite += aligned * weight
    
    return composite

# ==========================================
# 3. 主程序
# ==========================================
with st.spinner(" 正在从全球市场同步数据..."):
    data, errors = fetch_market_data()

if not data or "黄金" not in data:
    st.error(" 无法获取黄金核心数据，请检查网络连接（需科学上网）后刷新重试。")
    st.stop()

if errors:
    st.warning(f"️ 以下因子数据暂时不可用，分析将基于可用因子进行：{', '.join(errors)}")

# 计算因子
factors = calculate_factors(data)
composite_score = calculate_composite_score(factors)

gold_price = data["黄金"]

# ==========================================
# 4. 界面展示
# ==========================================
st.markdown("---")

# --- 4.1 核心指标卡片 ---
st.subheader(" 黄金综合预测指数 (GPI)")

latest_score = composite_score.iloc[-1]
gold_current = gold_price.iloc[-1]
gold_change = (gold_price.iloc[-1] - gold_price.iloc[-5]) / gold_price.iloc[-6] * 100

# 判断趋势区间
if latest_score >= 70:
    trend_label = "🟢 强看涨"
    trend_desc = "多因子共振，黄金处于强势上涨通道"
elif latest_score >= 55:
    trend_label = "🟡 偏多震荡"
    trend_desc = "整体偏多，但部分因子存在分歧"
elif latest_score >= 40:
    trend_label = "🟠 中性震荡"
    trend_desc = "多空力量均衡，方向不明朗"
else:
    trend_label = " 偏空承压"
    trend_desc = "多重压力叠加，黄金面临回调风险"

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("当前金价 (COMEX)", f"${gold_current:,.2f}", f"{gold_change:+.2f}%")
with col2:
    st.metric("综合预测指数 (GPI)", f"{latest_score:.1f}", trend_label)
with col3:
    # 计算均线偏离度
    ma30 = gold_price.rolling(30).mean().iloc[-1]
    deviation = (gold_current - ma30) / ma30 * 100
    st.metric("30日均线偏离度", f"{deviation:+.2f}%", help="正值=价格高于均线")
with col4:
    # 近20日波动率
    volatility = gold_price.pct_change().tail(20).std() * np.sqrt(252) * 100
    st.metric("年化波动率", f"{volatility:.1f}%", help="衡量近期价格波动剧烈程度")

st.info(f"**趋势研判**：{trend_desc}")

st.markdown("---")

# --- 4.2 黄金价格与GPI叠加图 ---
st.subheader(" 黄金价格走势 vs 综合预测指数")

fig_main = make_subplots(specs=)

fig_main.add_trace(
    go.Scatter(x=gold_price.index, y=gold_price, name="黄金价格 (USD/oz)", 
               line=dict(color='#FFD700', width=2.5)),
    secondary_y=False,
)

fig_main.add_trace(
    go.Scatter(x=composite_score.index, y=composite_score, name="GPI 综合预测指数", 
               line=dict(color='#FF6B6B', width=2, dash='dot'), fill='tozeroy',
               fillcolor='rgba(255,107,107,0.1)'),
    secondary_y=True,
)

# 添加GPI区间参考线
for threshold, color, label in :
    fig_main.add_hline(y=threshold, line_dash="dash", line_color=color, 
                       annotation_text=label, annotation_position="right",
                       secondary_y=True)

fig_main.update_layout(height=500, hovermode='x unified', template="plotly_dark")
fig_main.update_yaxes(title_text="黄金价格 (USD)", secondary_y=False)
fig_main.update_yaxes(title_text="GPI 指数 (0-100)", secondary_y=True, range=[0, 100])

st.plotly_chart(fig_main, use_container_width=True)

st.markdown("---")

# --- 4.3 各因子雷达图 ---
st.subheader(" 六大因子当前状态雷达图")

factor_names = list(factors.keys())
factor_values = [factors[f].iloc[-1] for f in factor_names]

fig_radar = go.Figure(data=go.Scatterpolar(
    r=factor_values + [factor_values[0]],  # 闭合
    theta=factor_names + [factor_names[0]],
    fill='toself',
    fillcolor='rgba(255, 215, 0, 0.3)',
    line=dict(color='#FFD700', width=2),
    name='当前因子状态'
))

fig_radar.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 100]),
        bgcolor='rgba(0,0,0,0)'
    ),
    height=500,
    template="plotly_dark"
)

st.plotly_chart(fig_radar, use_container_width=True)

st.markdown("---")

# --- 4.4 各因子走势详情 ---
st.subheader(" 各因子历史走势详情")

selected_factors = st.multiselect(
    "选择要查看的因子（可多选）",
    options=factor_names,
    default=factor_names[:3]
)

if selected_factors:
    fig_factors = go.Figure()
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
    
    for i, factor_name in enumerate(selected_factors):
        fig_factors.add_trace(go.Scatter(
            x=factors[factor_name].index,
            y=factors[factor_name],
            name=factor_name,
            line=dict(color=colors[i % len(colors)], width=1.5)
        ))
    
    fig_factors.update_layout(height=400, template="plotly_dark", hovermode='x unified')
    st.plotly_chart(fig_factors, use_container_width=True)

st.markdown("---")

# --- 4.5 因子相关性矩阵 ---
st.subheader(" 因子间相关性矩阵")

factor_df = pd.DataFrame(factors)
corr = factor_df.corr()

fig_corr = go.Figure(data=go.Heatmap(
    z=corr.values,
    x=corr.columns,
    y=corr.index,
    colorscale='RdBu_r',
    zmid=0,
    text=corr.round(2).astype(str),
    texttemplate='%{text}',
    textfont={"size": 11}
))
fig_corr.update_layout(height=500, template="plotly_dark")
st.plotly_chart(fig_corr, use_container_width=True)

st.markdown("---")

# --- 4.6 分析报告摘要 ---
st.subheader(" 多因子分析报告摘要")

# 找出最强和最弱的因子
sorted_factors = sorted(factors.items(), key=lambda x: x[1].iloc[-1], reverse=True)
strongest = sorted_factors[0]
weakest = sorted_factors[-1]

report = f"""
**分析时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}

**综合研判**：
- 当前GPI指数为 **{latest_score:.1f}**，处于 **{trend_label}** 区间
- {trend_desc}

**因子状态**：
- 🟢 最强支撑因子：**{strongest[0]}**（得分 {strongest[1].iloc[-1]:.1f}）
-  最弱拖累因子：**{weakest[0]}**（得分 {weakest[1].iloc[-1]:.1f}）

**模型说明**：
- 底层锚定层（美元信用 + 实际利率）权重 45%，决定长期趋势方向
- 边际催化层（金融情绪 + 通胀预期 + 游资动向 + 避险需求）权重 55%，驱动中短期波动
- 当GPI ≥ 70时，多因子共振形成强上涨信号；GPI ≤ 40时，面临趋势性回调风险

️ **风险提示**：本模型基于历史数据量化分析，不构成投资建议。地缘政治突发事件可能导致模型短期失效。
"""

st.markdown(report)
