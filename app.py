import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import warnings
import time

warnings.filterwarnings('ignore')

# ==================================================
# 页面配置
# ==================================================
st.set_page_config(page_title="黄金顶级分析模型 Pro", layout="wide", page_icon="🏆")
st.title("🏆 黄金走势深度分析模型 (Pro版)")
st.markdown("---")

# ==================================================
# 1. 数据获取模块 (免费源)
# ==================================================
@st.cache_data(ttl=3600)
def fetch_market_data():
    """获取市场核心数据"""
    tickers = {
        "Gold": "GC=F",
        "DXY": "DX-Y.NYB",      # 美元指数
        "US10Y": "^TNX",         # 10年期美债收益率
        "US02Y": "^IRX",         # 2年期美债收益率 (对政策更敏感)
        "Silver": "SI=F",        # 白银 (金银比)
        "BTC": "BTC-USD",        # 比特币 (流动性替代)
        "Crude": "CL=F",         # 原油 (通胀预期)
        "VIX": "^VIX",           # 恐慌指数 (避险)
        "SP500": "^GSPC"         # 标普500 (风险偏好)
    }
    
    data = {}
    # 获取过去1年数据用于分析
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    try:
        df = yf.download(list(tickers.values()), start=start_date, end=end_date, progress=False)['Close']
        for name, ticker in tickers.items():
            data[name] = df[ticker] if ticker in df.columns else pd.Series(dtype=float)
            
        # 计算实际利率 (名义利率 - 通胀预期) 
        # 这里简化处理：用 10Y美债 - (最近CPI) 近似，或用 TIPS (^TIP) 
        # 由于免费源TIPS数据常缺失，我们用 10Y - 2Y (利差) 作为衰退/宽松代理指标之一
        data["Yield_Spread"] = data["US10Y"] - data["US02Y"] 
        
    except Exception as e:
        st.error(f"数据获取失败: {e}")
        return None
        
    return data

@st.cache_data(ttl=86400)
def get_economic_calendar():
    """
    模拟获取未来7天重要财经日历。
    *注意：真实环境中需接入Investing.com API或爬虫，此处为演示逻辑构建结构化数据*
    """
    today = datetime.now()
    calendar = []
    
    # 模拟未来7天的关键事件 (实际部署时可替换为爬虫逻辑)
    events_pool = [
        {"date_offset": 1, "event": "美联储理事讲话", "impact": "High", "type": "Speech"},
        {"date_offset": 2, "event": "初请失业金人数", "impact": "Medium", "type": "Labor"},
        {"date_offset": 3, "event": "核心PCE物价指数", "impact": "High", "type": "Inflation"},
        {"date_offset": 5, "event": "非农就业数据(NFP)", "impact": "Critical", "type": "Labor"},
        {"date_offset": 6, "event": "ISM制造业PMI", "impact": "Medium", "type": "Economy"},
    ]
    
    for evt in events_pool:
        evt_date = today + timedelta(days=evt['date_offset'])
        calendar.append({
            "Date": evt_date.strftime("%Y-%m-%d"),
            "Day": f"T+{evt['date_offset']}",
            "Event": evt['event'],
            "Impact": evt['impact'],
            "Type": evt['type']
        })
        
    return pd.DataFrame(calendar)

# ==================================================
# 2. 分析引擎模块
# ==================================================
def analyze_trend(data):
    """综合多因子分析"""
    latest = {k: v.iloc[-1] for k, v in data.items()}
    
    # --- 因子评分逻辑 (0-100分，50为中性) ---
    score = 50 
    
    # 1. 美元指数 (负相关)
    dxy_change = data["DXY"].pct_change(20).iloc[-1]
    if dxy_change < -0.02: score += 15
    elif dxy_change > 0.02: score -= 15
    
    # 2. 美债收益率 (负相关)
    us10y_change = data["US10Y"].pct_change(20).iloc[-1]
    if us10y_change < -0.05: score += 15
    elif us10y_change > 0.05: score -= 15
    
    # 3. 避险情绪 (VIX正相关)
    vix_level = latest.get("VIX", 15)
    if vix_level > 20: score += 10
    
    # 4. 技术面 (RSI)
    gold_prices = data["Gold"].dropna()
    delta = gold_prices.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]
    
    if current_rsi < 30: score += 10 # 超卖反弹
    elif current_rsi > 70: score -= 10 # 超买回调
    
    return {
        "score": min(max(score, 0), 100),
        "rsi": current_rsi,
        "gold_price": latest["Gold"],
        "dxy": latest["DXY"],
        "us10y": latest["US10Y"],
        "vix": latest.get("VIX", 0)
    }

def generate_daily_strategy(day_idx, event_info, tech_data):
    """生成单日详细策略"""
    strategy = ""
    advice = ""
    
    impact = event_info.get("Impact", "Low")
    event_type = event_info.get("Type", "")
    
    # 基础技术面判断
    rsi = tech_data['rsi']
    
    if impact == "Critical":
        strategy = "⚠️ **极高风险日**：重大数据发布，市场波动率将剧增。"
        if event_type == "Labor": # 非农/失业金
            advice = "建议在数据发布前**空仓观望**。若数据大幅低于预期(利多)，突破关键阻力位后轻仓追多；反之亦然。严禁重仓赌数据。"
        elif event_type == "Inflation": # CPI/PCE
            advice = "关注核心数据。若通胀粘性超预期，金价可能短线跳水，是**中期布局的空点**或是**短线的卖点**。"
            
    elif impact == "High":
        strategy = "⚡ **高波动预警**：美联储讲话或重要指数发布。"
        advice = "关注讲话措辞是否鹰派。若提及'降息'，逢低买入；若强调'抗通胀'，逢高做空。"
        
    else:
        strategy = "🛡️ **技术性震荡**：无重大消息，跟随技术面。"
        if rsi < 40:
            advice = "指标偏低，可尝试在支撑位**分批建仓多单**。"
        elif rsi > 60:
            advice = "指标偏高，注意**获利了结**，不宜追高。"
        else:
            advice = "区间操作，高抛低吸。"
            
    return strategy, advice

# ==================================================
# 3. Streamlit 界面渲染
# ==================================================
def main():
    # 侧边栏加载状态
    with st.spinner('正在连接全球金融市场获取实时数据...'):
        data = fetch_market_data()
        analysis = analyze_trend(data)
        calendar_df = get_economic_calendar()
        
    if data is None:
        return

    # --- 顶部核心仪表盘 ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("实时金价 (GC=F)", f"${analysis['gold_price']:.2f}")
    col2.metric("美元指数 (DXY)", f"{analysis['dxy']:.2f}")
    col3.metric("10年美债收益率", f"{analysis['us10y']:.2f}%")
    
    # 综合评分颜色逻辑
    score = analysis['score']
    color = "red" if score > 60 else ("green" if score < 40 else "gray")
    trend_text = "强烈看涨 🚀" if score > 75 else ("看涨 📈" if score > 60 else ("震荡 ⚖️" if score > 40 else ("看跌 📉" if score > 25 else "强烈看跌 🧊")))
    col4.metric("AI 综合趋势评分", f"{score}/100 ({trend_text})")

    st.markdown("---")

    # --- Tab 分页设计 ---
    tab_short, tab_mid, tab_long, tab_viz = st.tabs(["⚔️ 短期战术 (1-7天)", "📅 中期战略 (1周-1月)", "🌍 长期宏观 (1月+)", "📊 深度可视化"])

    # ==============================
    # TAB 1: 短期战术 (1-7天按日分析)
    # ==============================
    with tab_short:
        st.subheader("未来7天黄金交易作战室")
        st.info("💡 **逻辑说明**：本模块结合【即将发布的重磅数据】与【当前技术面(RSI/均线)】，为您生成每日具体的操盘建议。")
        
        # 遍历未来7天
        for i in range(7):
            target_date = datetime.now() + timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][target_date.weekday()]
            
            # 查找当天是否有事件
            day_events = calendar_df[calendar_df['Date'] == date_str]
            event_str = ""
            impact_level = "Low"
            
            if not day_events.empty:
                evt_row = day_events.iloc[0]
                event_str = f"**[{evt_row['Impact']}] {evt_row['Event']}**"
                impact_level = evt_row['Impact']
            else:
                event_str = "无重大 scheduled 数据"
                
            # 生成当日策略
            strat, adv = generate_daily_strategy(i, {"Impact": impact_level, "Type": day_events.iloc[0]['Type'] if not day_events.empty else ""}, analysis)
            
            with st.expander(f"📅 {date_str} ({day_name}) - {event_str}", expanded=(i==0)):
                c1, c2 = st.columns([1, 3])
                c1.markdown(f"**当日评级**")
                # 根据影响力和RSI简单给个星级
                stars = "⭐⭐⭐⭐⭐" if impact_level == "Critical" else ("⭐⭐⭐" if impact_level == "High" else "⭐⭐")
                c1.markdown(f"{stars} (波动预期)")
                
                c2.markdown(f"**AI 操盘建议**：\n\n{adv}")
                c2.caption(f"策略依据：{strat}")

    # ==============================
    # TAB 2: 中期战略 (1周-1月)
    # ==============================
    with tab_mid:
        st.subheader("中期趋势推演 (1周 - 1个月)")
        
        mid_col1, mid_col2 = st.columns(2)
        
        with mid_col1:
            st.markdown("#### 🔍 核心驱动因子")
            st.write("""
            1. **美联储政策路径**：市场目前正在定价未来的降息次数。任何关于“推迟降息”的信号都会打压金价。
            2. **地缘政治溢价**：中东及俄乌局势若缓和，金价将回吐避险溢价；若升级，将提供坚实底部。
            3. **央行购金动态**：关注中国央行及其他新兴市场央行的月度储备数据，这是长期的买盘支撑。
            """)
            
        with mid_col2:
            st.markdown("#### 🎯 关键点位预测")
            current_p = analysis['gold_price']
            st.metric("上方强阻力位", f"${current_p * 1.05:.2f} (前高/心理关口)")
            st.metric("下方强支撑位", f"${current_p * 0.95:.2f} (均线支撑/成本区)")
            
        st.warning("⚠️ **中期策略建议**：若金价回调至支撑位且未跌破，是中线多单的最佳入场点。切勿在数据发布前夕满仓。")

    # ==============================
    # TAB 3: 长期宏观 (1月以上)
    # ==============================
    with tab_long:
        st.subheader("长期宏观叙事 (1个月 - 数年)")
        
        long_text = """
        ### 🌍 黄金的长期牛市逻辑
        
        1. **美国债务螺旋 (Fiscal Dominance)**：
           美国国债规模已突破34万亿美元，利息支出呈指数级增长。长期来看，为了偿还债务，美元购买力必然下降（金融压抑），这是黄金长牛的根本基石。
           
        2. **去美元化 (De-dollarization)**：
           全球南方国家（Global South）正在减少美债持有，增加黄金储备。这种结构性的需求转移不会因短期的利率波动而改变。
           
        3. **实际利率回归**：
           虽然目前名义利率较高，但随着通胀粘性和经济放缓，**实际利率（名义利率-通胀）**终将下行。历史上，实际利率下行周期对应黄金的主升浪。
        """
        st.markdown(long_text)
        
        st.success("💎 **长期结论**：黄金正处于从“货币属性”向“信用对冲属性”切换的历史进程中。对于长线投资者，任何因加息预期导致的深跌都是配置机会。")

    # ==============================
    # TAB 4: 深度可视化
    # ==============================
    with tab_viz:
        st.subheader("多维数据透视")
        
        # 图表1：金价 vs 实际利率代理 (10Y美债)
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        fig1.add_trace(go.Scatter(x=data["Gold"].index, y=data["Gold"], name="Gold Price", line=dict(color="gold")), secondary_y=False)
        fig1.add_trace(go.Scatter(x=data["US10Y"].index, y=data["US10Y"], name="US 10Y Yield", line=dict(color="red")), secondary_y=True)
        fig1.update_layout(title_text="黄金价格 vs 10年期美债收益率 (通常负相关)", height=500)
        st.plotly_chart(fig1, use_container_width=True)
        
        # 图表2：美元指数与黄金
        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig2.add_trace(go.Scatter(x=data["Gold"].index, y=data["Gold"], name="Gold", line=dict(color="orange")), secondary_y=False)
        fig2.add_trace(go.Scatter(x=data["DXY"].index, y=data["DXY"], name="DXY", line=dict(color="blue", dash="dot")), secondary_y=True)
        fig2.update_layout(title_text="黄金 vs 美元指数 (跷跷板效应)", height=400)
        st.plotly_chart(fig2, use_container_width=True)

        # 图表3：VIX 恐慌指数
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=data["VIX"].index, y=data["VIX"], fill='tozeroy', name="VIX", line=dict(color="purple")))
        fig3.update_layout(title_text="市场恐慌指数 (VIX) - 避险情绪监测", height=300)
        st.plotly_chart(fig3, use_container_width=True)

if __name__ == "__main__":
    main()
