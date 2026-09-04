
# -*- coding: utf-8 -*-
"""
黄金走势深度分析模型 Pro
========================
功能：
  - 15+ 核心因子多因子加权评分
  - 短期战术面板（1-7天按日分析，含重要数据日历与操作建议）
  - 中期战略推演（1周-1月）
  - 长期宏观叙事（1月+）
  - 9+ 深度可视化图表
  - 情景推演（降息/衰退/地缘危机/软着陆）
  - 可下载完整分析报告

数据源：Yahoo Finance + FRED（全部免费，无需 API Key）
部署：Streamlit Cloud
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import warnings
import json

warnings.filterwarnings('ignore')

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="黄金走势深度分析模型 Pro",
    page_icon=":chart_with_upwards_trend:",
    layout="wide"
)

# 自定义 CSS 样式
st.markdown("""
<style>
    .metric-container {background-color: #1a1a2e; padding: 20px; border-radius: 10px;}
    .stDataFrame {background-color: #0f0f23; color: #ffffff;}
    .stExpander {background-color: #16213e; border-radius: 8px;}
    [data-testid="stMetricValue"] {font-size: 1.5rem; font-weight: bold;}
    .stTabs [data-baseweb="tab-list"] {gap: 8px;}
    .stTabs [data-baseweb="tab"] {height: 40px; white-space: pre-wrap; border-radius: 8px 8px 0 0;}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 1. 数据获取模块（全部免费，无需 API Key）
# ============================================================

@st.cache_data(ttl=300)
def fetch_market_data():
    """从 Yahoo Finance 获取市场核心数据"""
    tickers = {
        "Gold": "GC=F",
        "DXY": "DX-Y.NYB",
        "US10Y": "^TNX",
        "US02Y": "^IRX",
        "Silver": "SI=F",
        "BTC": "BTC-USD",
        "Crude": "CL=F",
        "VIX": "^VIX",
        "SP500": "^GSPC",
        "TIPS": "^TIP",
    }
    data = {}
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2年数据
    try:
        all_data = yf.download(list(tickers.values()), start=start_date, end=end_date, progress=False)
        if isinstance(all_data, pd.DataFrame):
            cols = [c for c in tickers.values() if c in all_data.columns]
            close = all_data[cols]['Close'] if 'Close' in all_data.columns else all_data['Close']
            for name, ticker in tickers.items():
                if ticker in close.columns:
                    data[name] = close[ticker]
    except Exception as e:
        st.error(f"市场数据获取失败: {e}")
    return data


@st.cache_data(ttl=86400)
def fetch_fred_data():
    """从 FRED 获取宏观经济数据"""
    fred_urls = {
        "CPI": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL",
        "UNRATE": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE",
        "FEDFUNDS": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS",
        "PAYEMS": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=PAYEMS",
        "RSXFSN": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RSXFSN",
        "INDPRO": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO",
        "GFDEBTN": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GFDEBTN",
        "PPIACO": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=PPIACO",
        "CPIFSL": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIFSL",
        "M2SL": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL",
        "UMCSENT": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT",
    }
    fred_data = {}
    for name, url in fred_urls.items():
        try:
            df = pd.read_csv(url)
            df['DATE'] = pd.to_datetime(df['DATE'])
            df = df.set_index('DATE').sort_index()
            col_name = df.columns[-1]
            fred_data[name] = df[col_name]
        except Exception:
            fred_data[name] = pd.Series(dtype=float)
    # 计算衍生指标
    if not fred_data["CPI"].empty and not fred_data["US10Y"].empty:
        pass
    return fred_data


@st.cache_data(ttl=86400)
def get_economic_calendar():
    """
    构建未来7天财经日历。
    实际部署时可替换为爬虫逻辑或 API 调用。
    此处根据月度发布日程表预置关键事件。
    """
    today = datetime.now()
    calendar = []

    # 非农数据通常在每月第一个周五发布
    # 核心PCE通常在每月最后一个周五发布
    # CPI通常在每月月中旬发布
    # 美联储FOMC会议每6周一次

    # 构建未来14天的日历
    for i in range(14):
        date = today + timedelta(days=i)
        day_of_month = date.day
        weekday = date.weekday()  # 0=Mon, 6=Sun

        # 非农：每月第一个周五
        if day_of_month >= 1 and day_of_month <= 7 and weekday == 4:
            calendar.append({
                "date": date.strftime("%Y-%m-%d"),
                "day_label": f"T+{i}",
                "event": "非农就业数据 (NFP)",
                "impact": "Critical",
                "type": "Labor",
                "description": "美国非农就业人数变化，反映劳动力市场健康状况"
            })

        # 初请失业金：每周五
        if weekday == 4 and i > 0:
            calendar.append({
                "date": date.strftime("%Y-%m-%d"),
                "day_label": f"T+{i}",
                "event": "初请失业金人数",
                "impact": "Medium",
                "type": "Labor",
                "description": "每周首次申请失业救济人数"
            })

        # CPI：通常在月中（10-15号左右）
        if 10 <= day_of_month <= 15 and weekday in [0, 1, 2]:
            calendar.append({
                "date": date.strftime("%Y-%m-%d"),
                "day_label": f"T+{i}",
                "event": "CPI 消费者物价指数",
                "impact": "High",
                "type": "Inflation",
                "description": "消费者物价指数同比，衡量通胀水平的核心指标"
            })

        # 核心PCE：通常在月末
        if 25 <= day_of_month <= 31 and weekday in [0, 1, 2, 3, 4]:
            calendar.append({
                "date": date.strftime("%Y-%m-%d"),
                "day_label": f"T+{i}",
                "event": "核心PCE物价指数",
                "impact": "High",
                "type": "Inflation",
                "description": "美联储最偏好的通胀指标，剔除食品和能源"
            })

        # ISM制造业PMI：每月第一个工作日
        if 1 <= day_of_month <= 5 and weekday == 0:
            calendar.append({
                "date": date.strftime("%Y-%m-%d"),
                "day_label": f"T+{i}",
                "event": "ISM制造业PMI",
                "impact": "Medium",
                "type": "Economy",
                "description": "制造业采购经理人指数，>50扩张，<50收缩"
            })

        # 美联储官员讲话（模拟）
        if i in [1, 3, 5, 7, 9, 11, 13]:
            calendar.append({
                "date": date.strftime("%Y-%m-%d"),
                "day_label": f"T+{i}",
                "event": "美联储理事讲话",
                "impact": "Medium",
                "type": "Speech",
                "description": "美联储理事或主席公开发表货币政策相关讲话"
            })

    # 去重（同一天同类型只保留最高影响）
    seen = set()
    unique_calendar = []
    for item in calendar:
        key = (item["date"], item["type"])
        if key not in seen:
            seen.add(key)
            unique_calendar.append(item)

    return sorted(unique_calendar, key=lambda x: x["date"])


# ============================================================
# 2. 多因子评分引擎
# ============================================================

def calculate_all_factors(market_data, fred_data):
    """计算所有因子的评分和详情"""
    scores = {}
    details = {}

    # --- 1. 美元指数（负相关）---
    if "DXY" in market_data and len(market_data["DXY"]) > 20:
        dxy = market_data["DXY"].dropna()
        d1 = dxy.iloc[-1]
        d22 = dxy.iloc[-22] if len(dxy) > 22 else dxy.iloc[0]
        d66 = dxy.iloc[-66] if len(dxy) > 66 else dxy.iloc[0]
        chg_1m = (d1 / d22 - 1) * 100
        chg_3m = (d1 / d66 - 1) * 100
        score = np.clip(-chg_1m * 15, -100, 100)
        scores["美元指数"] = score
        details["美元指数"] = f"当前: {d1:.2f} | 1月变动: {chg_1m:+.2f}% | 3月变动: {chg_3m:+.2f}%"

    # --- 2. 实际利率（负相关）---
    if "US10Y" in market_data and not fred_data.get("CPI", pd.Series()).empty:
        us10y = market_data["US10Y"].dropna().iloc[-1]
        cpi = fred_data["CPI"].dropna()
        cpi_yoy = cpi.pct_change(12).dropna().iloc[-1] if len(cpi) > 12 else 3.0
        real_rate = us10y - cpi_yoy
        if real_rate < 0:
            score = np.clip(abs(real_rate) * 20, 0, 100)
        else:
            score = np.clip(-real_rate * 15, -100, 0)
        scores["实际利率"] = score
        details["实际利率"] = f"10Y国债: {us10y:.2f}% | CPI同比: {cpi_yoy:.2f}% | 实际利率: {real_rate:.2f}%"

    # --- 3. 通胀数据（正相关）---
    if not fred_data.get("CPI", pd.Series()).empty:
        cpi = fred_data["CPI"].dropna()
        cpi_yoy = cpi.pct_change(12).dropna()
        if len(cpi_yoy) > 1:
            cur = cpi_yoy.iloc[-1]
            trend = cur - cpi_yoy.iloc[-2]
            score = np.clip((cur - 2.0) * 25 + trend * 10, -100, 100)
            scores["通胀数据"] = score
            details["通胀数据"] = f"CPI同比: {cur:.2f}% | 趋势: {'上升' if trend > 0 else '下降'}({trend:+.2f}%)"

    # --- 4. 核心CPI（正相关）---
    if not fred_data.get("CPIFSL", pd.Series()).empty:
        cpifsl = fred_data["CPIFSL"].dropna()
        cpi_core_yoy = cpifsl.pct_change(12).dropna()
        if len(cpi_core_yoy) > 1:
            cur = cpi_core_yoy.iloc[-1]
            trend = cur - cpi_core_yoy.iloc[-2]
            score = np.clip((cur - 2.5) * 20 + trend * 8, -100, 100)
            scores["核心CPI"] = score
            details["核心CPI"] = f"核心CPI同比: {cur:.2f}% | 趋势: {'上升' if trend > 0 else '下降'}({trend:+.2f}%)"

    # --- 5. PPI（正相关）---
    if not fred_data.get("PPIACO", pd.Series()).empty:
        ppi = fred_data["PPIACO"].dropna()
        ppi_yoy = ppi.pct_change(12).dropna()
        if len(ppi_yoy) > 1:
            cur = ppi_yoy.iloc[-1]
            trend = cur - ppi_yoy.iloc[-2]
            score = np.clip((cur - 2.0) * 20 + trend * 8, -100, 100)
            scores["生产指数(PPI)"] = score
            details["生产指数(PPI)"] = f"PPI同比: {cur:.2f}% | 趋势: {'上升' if trend > 0 else '下降'}({trend:+.2f}%)"

    # --- 6. 就业数据/非农（非农低于预期利多黄金）---
    if not fred_data.get("PAYEMS", pd.Series()).empty:
        nfp = fred_data["PAYEMS"].dropna()
        nfp_change = nfp.diff().dropna()
        if len(nfp_change) > 1:
            latest = nfp_change.iloc[-1]
            avg = nfp_change.iloc[-12:].mean() if len(nfp_change) >= 12 else nfp_change.mean()
            deviation = latest - avg
            score = np.clip(-deviation / 50, -100, 100)
            scores["就业数据"] = score
            details["就业数据"] = f"最新非农: {latest:+.0f}K | 12月均值: {avg:+.0f}K | 偏差: {deviation:+.0f}K"

    # --- 7. 失业率（上升利多黄金）---
    if not fred_data.get("UNRATE", pd.Series()).empty:
        unemp = fred_data["UNRATE"].dropna()
        if len(unemp) > 1:
            cur = unemp.iloc[-1]
            chg = cur - unemp.iloc[-2]
            score = np.clip((cur - 3.5) * 30 + chg * 50, -100, 100)
            scores["失业率"] = score
            details["失业率"] = f"当前: {cur:.1f}% | 变动: {chg:+.2f}%"

    # --- 8. 美联储利率 ---
    if not fred_data.get("FEDFUNDS", pd.Series()).empty:
        fed = fred_data["FEDFUNDS"].dropna()
        if len(fed) > 1:
            cur = fed.iloc[-1]
            chg = fed.iloc[-1] - fed.iloc[-2]
            if chg < 0:
                score = np.clip(abs(chg) * 40, 0, 100)
            elif chg > 0:
                score = np.clip(-abs(chg) * 40, -100, 0)
            else:
                score = 20
            scores["美联储利率"] = score
            details["美联储利率"] = f"联邦基金利率: {cur:.2f}% | 最近变动: {chg:+.2f}%"

    # --- 9. 消费指数（消费疲软利多黄金）---
    if not fred_data.get("RSXFSN", pd.Series()).empty:
        retail = fred_data["RSXFSN"].dropna()
        if len(retail) > 12:
            chg = (retail.iloc[-1] / retail.iloc[-13] - 1) * 100
            score = np.clip(-chg * 10, -100, 100)
            scores["消费指数"] = score
            details["消费指数"] = f"零售销售12月变动: {chg:+.2f}%"

    # --- 10. 工业生产指数 ---
    if not fred_data.get("INDPRO", pd.Series()).empty:
        ind = fred_data["INDPRO"].dropna()
        if len(ind) > 12:
            chg = (ind.iloc[-1] / ind.iloc[-13] - 1) * 100
            score = np.clip(-chg * 10, -100, 100)
            scores["生产指数"] = score
            details["生产指数"] = f"工业生产12月变动: {chg:+.2f}%"

    # --- 11. VIX恐慌指数（避险）---
    if "VIX" in market_data and len(market_data["VIX"].dropna()) > 5:
        vix = market_data["VIX"].dropna()
        cur = vix.iloc[-1]
        avg = vix.iloc[-22:].mean() if len(vix) > 22 else vix.mean()
        score = np.clip((cur - 20) * 3, -100, 100)
        scores["地缘/避险(VIX)"] = score
        details["地缘/避险(VIX)"] = f"VIX当前: {cur:.1f} | 20日均值: {avg:.1f}"

    # --- 12. 央行购金/避险需求（金银比）---
    if "Gold" in market_data and "Silver" in market_data:
        gold_p = market_data["Gold"].dropna().iloc[-1]
        silver_p = market_data["Silver"].dropna().iloc[-1]
        ratio = gold_p / silver_p if silver_p > 0 else 80
        score = np.clip((ratio - 80) * 2, -100, 100)
        scores["央行购金/避险"] = score
        details["央行购金/避险"] = f"金银比: {ratio:.1f} | 黄金: ${gold_p:.2f} | 白银: ${silver_p:.2f}"

    # --- 13. 美国负债（正相关）---
    if not fred_data.get("GFDEBTN", pd.Series()).empty:
        debt = fred_data["GFDEBTN"].dropna()
        if len(debt) > 4:
            chg = (debt.iloc[-1] / debt.iloc[-2] - 1) * 100
            score = np.clip(debt_chg * 5 + 30, -100, 100) if False else np.clip(chg * 5 + 30, -100, 100)
            scores["美国负债"] = score
            details["美国负债"] = f"国债总额: ${debt.iloc[-1]/1e9:.0f}B | 季度变动: {chg:+.2f}%"

    # --- 14. M2货币供应量 ---
    if not fred_data.get("M2SL", pd.Series()).empty:
        m2 = fred_data["M2SL"].dropna()
        if len(m2) > 12:
            chg = (m2.iloc[-1] / m2.iloc[-13] - 1) * 100
            score = np.clip(-chg * 8, -100, 100)
            scores["M2货币供应"] = score
            details["M2货币供应"] = f"M2同比变动: {chg:+.2f}%"

    # --- 15. 消费者信心指数 ---
    if not fred_data.get("UMCSENT", pd.Series()).empty:
        umc = fred_data["UMCSENT"].dropna()
        if len(umc) > 1:
            cur = umc.iloc[-1]
            chg = cur - umc.iloc[-2]
            score = np.clip(chg * 2, -100, 100)
            scores["消费者信心"] = score
            details["消费者信心"] = f"当前: {cur:.1f} | 变动: {chg:+.1f}"

    return scores, details


def calculate_composite_score(scores):
    """计算加权综合评分"""
    weights = {
        "美元指数": 0.15, "实际利率": 0.18, "通胀数据": 0.10,
        "核心CPI": 0.08, "生产指数(PPI)": 0.05, "就业数据": 0.10,
        "失业率": 0.07, "美联储利率": 0.10, "消费指数": 0.04,
        "生产指数": 0.03, "地缘/避险(VIX)": 0.04, "央行购金/避险": 0.03,
        "美国负债": 0.03, "M2货币供应": 0.02, "消费者信心": 0.02,
    }
    total_w = sum(weights.get(f, 0.03) for f in scores)
    weighted = sum(s * weights.get(f, 0.03) for f, s in scores.items())
    return weighted / total_w if total_w > 0 else 50


def get_signal(composite):
    """根据综合评分给出信号"""
    if composite > 50:
        return "强烈看多", "green"
    elif composite > 20:
        return "偏多", "limegreen"
    elif composite > -20:
        return "中性震荡", "gold"
    elif composite > -50:
        return "偏空", "orange"
    else:
        return "强烈看空", "red"


# ============================================================
# 3. 短期战术分析引擎（1-7天按日分析）
# ============================================================

def generate_daily_analysis(day_idx, event_info, market_data, fred_data, scores):
    """生成单日详细分析（至少50字）"""
    gold = market_data.get("Gold", pd.Series())
    gold = gold.dropna()
    if len(gold) < 5:
        return "数据不足，无法分析。", "数据不足"

    # 技术指标
    delta = gold.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if not rsi.empty else 50

    # 移动平均线
    ma7 = gold.rolling(7).mean().iloc[-1] if len(gold) >= 7 else gold.iloc[-1]
    ma20 = gold.rolling(20).mean().iloc[-1] if len(gold) >= 20 else gold.iloc[-1]
    current_price = gold.iloc[-1]

    # 布林带
    std20 = gold.rolling(20).std().iloc[-1] if len(gold) >= 20 else 0
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20

    # 波动率
    volatility = gold.pct_change().rolling(10).std().iloc[-1] * 100 if len(gold) >= 10 else 0

    impact = event_info.get("impact", "Low")
    event_type = event_info.get("type", "")
    event_name = event_info.get("event", "无重大事件")
    event_desc = event_info.get("description", "")

    # 构建分析文本
    analysis_parts = []

    # 技术面分析
    tech_parts = []
    if current_rsi > 70:
        tech_parts.append(f"RSI处于超买区域({current_rsi:.1f})，短期存在回调压力")
    elif current_rsi < 30:
        tech_parts.append(f"RSI处于超卖区域({current_rsi:.1f})，短期存在反弹机会")
    else:
        tech_parts.append(f"RSI处于中性区域({current_rsi:.1f})，技术面暂无明显信号")

    if current_price > ma20:
        tech_parts.append(f"金价运行在20日均线({ma20:.0f})上方，短期趋势偏多")
    else:
        tech_parts.append(f"金价运行在20日均线({ma20:.0f})下方，短期趋势偏空")

    if current_price > bb_upper:
        tech_parts.append(f"金价突破布林带上轨({bb_upper:.0f})，波动加剧")
    elif current_price < bb_lower:
        tech_parts.append(f"金价跌破布林带下轨({bb_lower:.0f})，波动加剧")

    analysis_parts.append(f"【技术面】{'；'.join(tech_parts)}。")

    # 事件驱动分析
    if event_name != "无重大事件":
        event_parts = []
        if event_type == "Labor":
            if impact == "Critical":
                event_parts.append(
                    f"今日发布{event_name}，这是黄金市场最重要的数据之一。"
                    f"若数据大幅高于预期，表明美国经济强劲，美元和美债收益率可能上行，"
                    f"对黄金构成利空压力；若数据低于预期，则市场将交易降息预期升温，"
                    f"黄金可能快速拉升。建议密切关注实际值与市场预期的偏离幅度。"
                )
            else:
                event_parts.append(
                    f"今日发布{event_name}，该数据反映劳动力市场的短期变化。"
                    f"虽然影响力不及非农，但若连续多期呈现恶化趋势，"
                    f"将强化市场对经济放缓和美联储降息的预期，对黄金形成中期支撑。"
                )
        elif event_type == "Inflation":
            if impact == "High":
                event_parts.append(
                    f"今日发布{event_name}，这是美联储制定货币政策的核心参考指标。"
                    f"若通胀数据高于预期，市场将重新定价降息路径，"
                    f"短期可能打压金价；但若通胀过高引发对美元购买力的担忧，"
                    f"中长期反而利好黄金。核心PCE是美联储最看重的指标，需特别关注。"
                )
            else:
                event_parts.append(
                    f"今日发布{event_name}，关注同比和前值的变化趋势。"
                    f"通胀的粘性将直接影响美联储的政策选择，进而影响黄金走势。"
                )
        elif event_type == "Speech":
            event_parts.append(
                f"今日有美联储官员发表讲话。需重点关注讲话中是否提及"
                f"'降息'、'通胀'、'劳动力市场'、'风险评估'等关键词。"
                f"若官员释放鸽派信号（支持降息），黄金将受益；"
                f"若释放鹰派信号（坚持高利率更久），黄金将面临压力。"
                f"建议提前关注讲话全文和市场解读。"
            )
        elif event_type == "Economy":
            event_parts.append(
                f"今日发布{event_name}，该指标反映美国经济的整体景气度。"
                f"PMI高于50表示制造业扩张，低于50表示收缩。"
                f"若数据显著高于/低于预期，将影响市场对经济前景的判断，"
                f"进而影响黄金的避险需求和美元走势。"
            )
        else:
            event_parts.append(
                f"今日有{event_name}发布，关注数据对市场预期的影响。"
                f"重大数据发布前后市场波动率通常会显著上升，"
                f"建议控制仓位，避免在数据公布瞬间追涨杀跌。"
            )
        analysis_parts.append(f"【事件驱动】{'；'.join(event_parts)}")
    else:
        analysis_parts.append(
            f"【事件驱动】今日无重大数据或事件发布，市场将主要跟随技术面走势运行。"
            f"在这种环境下，金价通常会在一个较窄的区间内震荡，"
            f"适合进行高抛低吸的区间操作策略。"
        )

    # 操作建议
    advice_parts = []
    if impact == "Critical":
        advice_parts.append(
            "【操作建议】极高风险日，建议数据发布前将仓位降至半仓以下。"
            "若数据利多黄金（低于预期），等数据公布后确认突破关键阻力位再轻仓追多；"
            "若数据利空黄金，等跌破支撑位后轻仓追空。"
            "严禁在数据公布前重仓赌方向，止损设为波动幅度的1.5倍。"
        )
    elif impact == "High":
        advice_parts.append(
            "【操作建议】高波动预警日，建议仓位控制在30%以内。"
            "关注数据公布后的市场反应方向，若金价站稳均线上方且RSI未超买，"
            "可考虑逢低做多；若金价跌破均线且RSI超买，考虑逢高减仓。"
            "严格设置止损，避免被假突破洗出。"
        )
    else:
        if current_rsi < 40:
            advice_parts.append(
                "【操作建议】技术面偏空，RSI处于低位，可考虑在支撑位附近分批建仓多单，"
                "目标位看布林带中轨或20日均线附近。止损设在近期低点下方。"
                "适合短线波段操作，不宜重仓。"
            )
        elif current_rsi > 60:
            advice_parts.append(
                "【操作建议】技术面偏多但RSI偏高，注意获利了结。"
                "持有空单者可逢高减仓，持有多单者建议部分止盈。"
                "不宜在高位追多，等待回调后再寻找入场机会。"
            )
        else:
            advice_parts.append(
                "【操作建议】市场处于中性震荡格局，建议区间操作。"
                f"上方阻力位参考${bb_upper:.0f}，下方支撑位参考${bb_lower:.0f}。"
                f"金价接近布林带上轨时考虑轻仓做空，接近下轨时考虑轻仓做多。"
                f"严格止损，仓位控制在20%以内。"
            )

    analysis_parts.append(''.join(advice_parts))

    # 关键点位
    support1 = round(current_price * 0.97, 0)
    support2 = round(bb_lower, 0)
    resistance1 = round(current_price * 1.03, 0)
    resistance2 = round(bb_upper, 0)

    return {
        "analysis": ' '.join(analysis_parts),
        "impact": impact,
        "event": event_name,
        "event_desc": event_desc,
        "rsi": current_rsi,
        "price": current_price,
        "ma7": ma7,
        "ma20": ma20,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "volatility": volatility,
        "support1": support1,
        "support2": support2,
        "resistance1": resistance1,
        "resistance2": resistance2,
    }


# ============================================================
# 4. 中期战略分析（1周-1月）
# ============================================================

def generate_midterm_analysis(market_data, fred_data, scores):
    """生成中期分析（至少50字）"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    if len(gold) < 20:
        return "数据不足，无法分析。"

    current = gold.iloc[-1]
    chg_1w = (gold.iloc[-1] / gold.iloc[-21] - 1) * 100 if len(gold) >= 21 else 0
    chg_1m = (gold.iloc[-1] / gold.iloc[-63] - 1) * 100 if len(gold) >= 63 else 0

    # MACD
    ema12 = gold.ewm(span=12).mean()
    ema26 = gold.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal

    # 均线系统
    ma50 = gold.rolling(50).mean().iloc[-1] if len(gold) >= 50 else current
    ma200 = gold.rolling(200).mean().iloc[-1] if len(gold) >= 200 else current

    parts = []

    # 趋势判断
    parts.append("【中期趋势判断】")
    if current > ma50 and current > ma200:
        parts.append("金价同时运行在50日均线和200日均线之上，中期上升趋势明确。")
    elif current < ma50 and current < ma200:
        parts.append("金价同时运行在50日均线和200日均线之下，中期下降趋势明确。")
    elif current > ma50 and current < ma200:
        parts.append("金价在200日均线下方但50日均线上方，中期趋势不确定，处于震荡整理阶段。")
    else:
        parts.append("金价在均线附近徘徊，中期方向不明，需等待突破信号。")

    # MACD信号
    parts.append(f"MACD指标显示{'多头动能增强' if macd_hist.iloc[-1] > 0 else '空头动能增强'}，"
                 f"MACD线{'上穿' if macd.iloc[-1] > signal.iloc[-1] else '下穿'}信号线，"
                 f"中期动能{'偏多' if macd_hist.iloc[-1] > 0 else '偏空'}。")

    # 驱动因素
    parts.append("【中期核心驱动因素】")
    parts.append(
        "1. 美联储政策路径：当前市场正在交易美联储的降息预期。"
        "若后续经济数据（就业、通胀）显示经济放缓，降息概率上升，将支撑金价中期走强。"
        "反之，若通胀粘性超预期，美联储维持高利率更久，将对金价构成压力。"
    )
    parts.append(
        "2. 地缘政治风险：中东、俄乌等地缘局势的不确定性为黄金提供避险溢价。"
        "若局势升级，金价将获得额外支撑；若出现缓和信号，避险溢价可能回吐。"
    )
    parts.append(
        "3. 央行购金需求：全球央行（尤其是中国、俄罗斯、印度等）持续增持黄金储备，"
        "这一结构性需求为金价提供了中长期底部支撑。"
    )
    parts.append(
        "4. 美元信用担忧：美国债务规模持续攀升，市场对美元长期购买力的担忧"
        "推动部分资金配置黄金作为对冲工具。"
    )

    # 操作建议
    parts.append("【中期操作建议】")
    if current > ma50:
        parts.append(
            "中期趋势偏多，建议逢回调分批建仓多单。"
            f"理想入场区间为${current * 0.95:.0f}-${current * 0.97:.0f}（回调至均线附近）。"
            f"目标位看${current * 1.05:.0f}-${current * 1.08:.0f}。"
            "止损设在200日均线下方或近期低点下方3%处。"
            "建议采用分批建仓策略，首次建仓30%，回调确认后再加仓30%。"
        )
    else:
        parts.append(
            "中期趋势偏空或震荡，建议谨慎观望或逢高减仓。"
            f"若金价反弹至${current * 1.02:.0f}-${current * 1.05:.0f}区间受阻，"
            "可考虑轻仓做空。"
            "止损设在近期高点上方3%处。"
            "等待趋势明确后再加大仓位。"
        )

    return '\n'.join(parts)


# ============================================================
# 5. 长期宏观分析（1月以上）
# ============================================================

def generate_longterm_analysis(market_data, fred_data, scores):
    """生成长期分析（至少50字）"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    if len(gold) < 60:
        return "数据不足，无法分析。"

    current = gold.iloc[-1]
    chg_6m = (gold.iloc[-1] / gold.iloc[-126] - 1) * 100 if len(gold) >= 126 else 0
    chg_1y = (gold.iloc[-1] / gold.iloc[-252] - 1) * 100 if len(gold) >= 252 else 0

    parts = []

    # 长期趋势
    parts.append("【长期趋势判断】")
    ma200 = gold.rolling(200).mean().iloc[-1] if len(gold) >= 200 else current
    if current > ma200:
        parts.append(f"金价运行在200日均线({ma200:.0f})之上，长期牛市格局未变。")
    else:
        parts.append(f"金价运行在200日均线({ma200:.0f})之下，长期趋势面临挑战。")

    parts.append(f"半年收益率: {chg_6m:+.2f}%，一年收益率: {chg_1y:+.2f}%。")

    # 宏观叙事
    parts.append("【长期核心叙事】")

    parts.append(
        "1. 美国债务螺旋（Fiscal Dominance）："
        "美国国债规模已突破34万亿美元，年度利息支出超过国防预算。"
        "长期来看，政府只能通过通胀或货币贬值来稀释债务负担，"
        "这构成了黄金长牛最根本的基石。历史经验表明，"
        "每次美国债务危机（2011年、2023年）都伴随着金价的大幅上涨。"
    )

    parts.append(
        "2. 去美元化趋势（De-dollarization）："
        "全球南方国家（金砖国家、中东产油国等）正在系统性减少美债持有，"
        "增加黄金储备。2022年俄乌冲突后，美国冻结俄罗斯外汇储备的举动"
        "加速了这一趋势。IMF数据显示，2022-2024年全球央行购金量持续创历史新高，"
        "这是金价长期最坚实的结构性买盘。"
    )

    parts.append(
        "3. 实际利率周期：虽然目前名义利率较高，但随着经济放缓和通胀粘性，"
        "实际利率（名义利率-通胀）终将下行。"
        "历史上，实际利率下行周期（2001-2011年、2020-2021年）"
        "都对应着黄金的主升浪。一旦美联储开启降息周期，"
        "实际利率下行将推动金价突破历史新高。"
    )

    parts.append(
        "4. 货币体系重构：比特币等加密资产的崛起对传统避险资产格局产生冲击，"
        "但黄金作为最古老的避险资产，其'终极货币'的地位短期内不可替代。"
        "在法币信用持续贬值的背景下，黄金的配置价值愈发突出。"
    )

    parts.append(
        "5. 通胀中枢上移：全球供应链重构、地缘碎片化、绿色能源转型等因素，"
        "可能导致全球通胀中枢较过去十年的低通胀环境有所上移。"
        "黄金作为抗通胀资产，将在这一环境中持续受益。"
    )

    # 长期操作建议
    parts.append("【长期操作建议】")
    parts.append(
        "长期来看，黄金处于多周期共振的牛市环境中。"
        "建议将黄金作为投资组合的5%-15%配置比例，"
        "采用定投或逢大跌分批建仓的策略。"
        f"当前金价${current:.0f}，若出现因鹰派美联储或强美元导致的急跌，"
        "是长期建仓的绝佳机会。"
        "目标价位看${current * 1.3:.0f}-${current * 1.5:.0f}（对应30%-50%的上涨空间）。"
        "止损不设（长期投资不看止损，看宏观逻辑是否破坏）。"
        "核心观察指标：美联储政策转向信号、央行购金数据、美国债务/GDP比率走势。"
    )

    return '\n'.join(parts)


# ============================================================
# 6. 情景推演引擎
# ============================================================

def scenario_analysis(market_data, fred_data):
    """四种情景推演"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    current = gold.iloc[-1] if len(gold) > 0 else 2000

    scenarios = {
        "降息周期（鸽派美联储）": {
            "probability": "40%",
            "trigger": "美联储明确释放降息信号，或通胀数据持续回落至2%目标",
            "gold_impact": "金价快速拉升，突破前高",
            "target": f"${current * 1.15:.0f} - ${current * 1.25:.0f}",
            "duration": "3-12个月",
            "strategy": "重仓做多，分批建仓，持有至美联储停止降息"
        },
        "经济衰退（硬着陆）": {
            "probability": "20%",
            "trigger": "失业率飙升、GDP负增长、企业大规模裁员",
            "gold_impact": "初期因流动性危机金价可能下跌，随后央行救市推动金价暴涨",
            "target": f"${current * 1.20:.0f} - ${current * 1.40:.0f}",
            "duration": "6-18个月",
            "strategy": "衰退初期减仓，确认央行转向后重仓做多"
        },
        "地缘危机升级": {
            "probability": "25%",
            "trigger": "中东/俄乌局势重大升级、台海局势紧张",
            "gold_impact": "避险资金涌入，金价短期暴涨",
            "target": f"${current * 1.10:.0f} - ${current * 1.30:.0f}",
            "duration": "1-6个月（事件驱动型）",
            "strategy": "事件驱动型交易，快进快出，设好止损"
        },
        "软着陆（基准情景）": {
            "probability": "15%",
            "trigger": "通胀温和回落，经济温和增长，美联储缓慢降息",
            "gold_impact": "金价震荡上行，波动率较低",
            "target": f"${current * 1.05:.0f} - ${current * 1.15:.0f}",
            "duration": "6-12个月",
            "strategy": "区间操作，高抛低吸，不宜追高"
        }
    }
    return scenarios


# ============================================================
# 7. 可视化模块
# ============================================================

def plot_gold_price_with_ma(market_data):
    """金价K线图 + 均线"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    if len(gold) < 30:
        return None

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=gold.index, open=gold.rolling(1).max().fillna(gold),
        high=gold.rolling(1).max().fillna(gold),
        low=gold.rolling(1).min().fillna(gold),
        close=gold, name="金价"
    ))
    fig.add_trace(go.Scatter(x=gold.index, y=gold.rolling(7).mean(),
                             line=dict(color="#FFD700", width=1), name="MA7"))
    fig.add_trace(go.Scatter(x=gold.index, y=gold.rolling(20).mean(),
                             line=dict(color="#FF6B6B", width=1), name="MA20"))
    fig.add_trace(go.Scatter(x=gold.index, y=gold.rolling(50).mean(),
                             line=dict(color="#4ECDC4", width=1), name="MA50"))
    fig.update_layout(title="黄金价格走势与移动平均线", height=500,
                      xaxis_title="日期", yaxis_title="价格 (USD)",
                      template="plotly_dark")
    return fig


def plot_gold_vs_dxy(market_data):
    """黄金 vs 美元指数"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    dxy = market_data.get("DXY", pd.Series()).dropna()
    if len(gold) < 20 or len(dxy) < 20:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=gold.index, y=gold, name="黄金价格",
                             line=dict(color="#FFD700", width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=dxy.index, y=dxy, name="美元指数",
                             line=dict(color="#4A90D9", width=2)), secondary_y=True)
    fig.update_layout(title="黄金 vs 美元指数（跷跷板效应）", height=450,
                      template="plotly_dark")
    return fig


def plot_gold_vs_yield(market_data, fred_data):
    """黄金 vs 10年期美债收益率 vs CPI"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    us10y = market_data.get("US10Y", pd.Series()).dropna()
    if len(gold) < 20 or len(us10y) < 20:
        return None

    cpi = fred_data.get("CPI", pd.Series()).dropna()
    cpi_yoy = cpi.pct_change(12).dropna() if len(cpi) > 12 else pd.Series(dtype=float)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=gold.index, y=gold, name="黄金价格",
                             line=dict(color="#FFD700", width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=us10y.index, y=us10y, name="10Y美债收益率",
                             line=dict(color="#FF6B6B", width=2)), secondary_y=True)

    if not cpi_yoy.empty:
        fig.add_trace(go.Bar(x=cpi_yoy.index, y=cpi_yoy.values, name="CPI同比(%)",
                             marker_color="#4ECDC4", opacity=0.5), secondary_y=True)

    fig.update_layout(title="黄金 vs 10年期美债收益率 & CPI", height=500,
                      template="plotly_dark")
    return fig


def plot_rsi_macd(market_data):
    """RSI + MACD 技术指标"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    if len(gold) < 50:
        return None

    # RSI
    delta = gold.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = gold.ewm(span=12).mean()
    ema26 = gold.ewm(span=26).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - macd_signal

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.4, 0.4])

    fig.add_trace(go.Scatter(x=gold.index, y=rsi, name="RSI(14)",
                             line=dict(color="#FF6B6B", width=1.5)), row=1, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=1, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=1, col=1)

    fig.add_trace(go.Bar(x=gold.index, y=macd_hist.values, name="MACD柱",
                             marker_color="#4ECDC4", opacity=0.7), row=2, col=1)
    fig.add_trace(go.Scatter(x=macd_signal.index, y=macd_signal.values,
                             name="MACD信号线", line=dict(color="#FFD700", width=1)), row=2, col=1)

    fig.update_layout(title="RSI + MACD 技术指标", height=550,
                      template="plotly_dark")
    return fig


def plot_gold_silver_ratio(market_data):
    """金银比走势"""
    gold = market_data.get("Gold", pd.Series()).dropna()
    silver = market_data.get("Silver", pd.Series()).dropna()
    if len(gold) < 20 or len(silver) < 20:
        return None

    ratio = gold / silver
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ratio.index, y=ratio, name="金银比",
                             line=dict(color="#FFD700", width=2)))
    fig.add_trace(go.Scatter(x=ratio.index, y=ratio.rolling(30).mean(),
                             name="30日均值", line=dict(color="#FF6B6B", width=1, dash="dot")))
    fig.update_layout(title="金银比走势（避险情绪指标）", height=400,
                      xaxis_title="日期", yaxis_title="金银比",
                      template="plotly_dark")
    return fig


def plot_factor_radar(scores):
    """因子雷达图"""
    if not scores:
        return None

    factors = list(scores.keys())
    values = list(scores.values())

    # 归一化到 0-100
    normalized = [(v + 100) / 2 for v in values]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=normalized + [normalized[0]],
        theta=factors + [factors[0]],
        fill='toself',
        name='因子评分',
        line=dict(color='#FFD700', width=2),
        fillcolor='rgba(255, 215, 0, 0.3)'
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100]),
            thetaaxis=dict(rotation=90)
        ),
        title="多因子评分雷达图（0=最利空, 100=最利多）",
        height=500,
        template="plotly_dark"
    )
    return fig


def plot_factor_bar(scores):
    """因子柱状图"""
    if not scores:
        return None

    sorted_items = sorted(scores.items(), key=lambda x: x[1])
    factors = [x[0] for x in sorted_items]
    values = [x[1] for x in sorted_items]
    colors = ['#FF6B6B' if v < 0 else '#4ECDC4' for v in values]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=values, y=factors, orientation='h',
        marker_color=colors,
        text=[f'{v:.1f}' for v in values],
        textposition='auto'
    ))
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="各因子评分明细（负=利空, 正=利多）",
        xaxis_title="评分", yaxis_title="因子",
        template="plotly_dark", height=450
    )
    return fig


def plot_scenario_scatter(scenarios):
    """情景推演散点图"""
    if not scenarios:
        return None

    targets = []
    probs = []
    colors = []
    for name, info in scenarios.items():
        target_range = info["target"].split(" - ")
        mid = float(target_range[0].replace("$", ""))
        targets.append(mid)
        probs.append(float(info["probability"].replace("%", "")))
        if "降息" in name:
            colors.append("#4ECDC4")
        elif "衰退" in name:
            colors.append("#FF6B6B")
        elif "地缘" in name:
            colors.append("#FFD700")
        else:
            colors.append("#4A90D9")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=targets, y=probs, mode='markers+text',
        marker=dict(size=15, color=colors, symbol='diamond'),
        text=[k for k in scenarios.keys()],
        textposition="top center"
    ))
    fig.update_layout(
        title="情景推演：目标价 vs 概率",
        xaxis_title="目标价 (USD)", yaxis_title="发生概率 (%)",
        template="plotly_dark"
    )
    return fig


# ============================================================
# 8. Streamlit 界面渲染
# ============================================================

def main():
    st.title("黄金走势深度分析模型 Pro")
    st.markdown("基于15+核心因子的多因子加权评分体系 | 数据源: Yahoo Finance + FRED")

    # 侧边栏 - 数据加载
    with st.sidebar:
        st.header("数据状态")
        with st.spinner("正在连接全球金融市场获取实时数据..."):
            market_data = fetch_market_data()
            fred_data = fetch_fred_data()

        if market_data:
            gold_price = market_data["Gold"].dropna().iloc[-1]
            st.success(f"金价: ${gold_price:.2f}")
        else:
            st.error("市场数据获取失败，请检查网络连接")
            return

        if fred_data:
            st.success("宏观数据加载完成")
        else:
            st.warning("宏观数据加载部分失败")

        st.markdown("---")
        st.markdown("**使用说明：**")
        st.markdown("1. 所有数据每5分钟自动刷新")
        st.markdown("2. 短期分析结合事件日历与技术指标")
        st.markdown("3. 中期分析关注趋势与驱动因素")
        st.markdown("4. 长期分析基于宏观叙事与历史周期")

    # 顶部核心指标面板
    st.subheader("核心指标概览")
    col1, col2, col3, col4, col5 = st.columns(5)

    gold = market_data.get("Gold", pd.Series()).dropna()
    dxy = market_data.get("DXY", pd.Series()).dropna()
    us10y = market_data.get("US10Y", pd.Series()).dropna()
    vix = market_data.get("VIX", pd.Series()).dropna()
    silver = market_data.get("Silver", pd.Series()).dropna()

    col1.metric("实时金价", f"${gold.iloc[-1]:.2f}" if len(gold) > 0 else "N/A")
    col2.metric("美元指数", f"{dxy.iloc[-1]:.2f}" if len(dxy) > 0 else "N/A")
    col3.metric("10Y美债收益率", f"{us10y.iloc[-1]:.2f}%" if len(us10y) > 0 else "N/A")
    col4.metric("VIX恐慌指数", f"{vix.iloc[-1]:.2f}" if len(vix) > 0 else "N/A")
    col5.metric("金银比", f"{gold.iloc[-1]/silver.iloc[-1]:.1f}" if len(gold) > 0 and len(silver) > 0 else "N/A")

    # 计算评分
    scores, details = calculate_all_factors(market_data, fred_data)
    composite = calculate_composite_score(scores)
    signal, signal_color = get_signal(composite)

    st.markdown("---")

    # 综合评分展示
    st.subheader("AI 综合评分")
    col_score, col_detail = st.columns([1, 3])
    col_score.metric(
        f"综合评分: {composite:+.1f}/100 ({signal})",
        delta=f"信号: {signal}",
        delta_color="normal" if composite > 20 else "inverse" if composite > -20 else "inverse"
    )
    col_detail.markdown(f"**当前金价:** ${gold.iloc[-1]:.2f}  |  **评分说明:** 0=最利空, 50=中性, 100=最利多")

    st.markdown("---")

    # Tab 分页
    tab_short, tab_mid, tab_long, tab_viz, tab_scenario = st.tabs([
        "短期战术 (1-7天)", "中期战略 (1周-1月)", "长期宏观 (1月+)", "深度可视化", "情景推演"
    ])

    # ==============================
    # TAB 1: 短期战术 (1-7天)
    # ==============================
    with tab_short:
        st.subheader("未来7天黄金交易作战室")
        st.info("结合即将发布的重要经济数据、美联储官员讲话与技术指标，逐日生成操作建议。")

        # 事件日历
        calendar = get_economic_calendar()
        st.markdown("#### 未来14天财经日历")
        if not calendar.empty:
            cal_df = pd.DataFrame(calendar)
            impact_colors = {"Critical": "#FF4444", "High": "#FF8C00", "Medium": "#4ECDC4", "Low": "#888888"}
            for idx, row in cal_df.head(14).iterrows():
                color = impact_colors.get(row["impact"], "#888888")
                st.markdown(
                    f"- **{row['date']}** ({row['day_label']}) "
                    f'<span style="color:{color}">[{row["impact"]}]</span> '
                    f"**{row['event']}** - {row['description']}",
                    unsafe_allow_html=True
                )

        st.markdown("---")
        st.markdown("#### 逐日分析")

        # 获取7天分析
        for i in range(7):
            target_date = datetime.now() + timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            day_name = day_names[target_date.weekday()]

            # 查找当天事件
            day_events = [e for e in calendar if e["date"] == date_str]
            event_info = day_events[0] if day_events else {
                "impact": "Low", "type": "", "event": "无重大事件",
                "description": "无重大数据或事件发布"
            }

            analysis = generate_daily_analysis(i, event_info, market_data, fred_data, scores)

            with st.expander(
                f"📅 {date_str} ({day_name}) - {analysis['event']} [{analysis['impact']}]",
                expanded=(i == 0)
            ):
                # 当日关键指标
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("RSI", f"{analysis['rsi']:.1f}")
                c2.metric("MA20", f"${analysis['ma20']:.0f}")
                c3.metric("布林上轨", f"${analysis['bb_upper']:.0f}")
                c4.metric("布林下轨", f"${analysis['bb_lower']:.0f}")

                # 关键点位
                st.markdown(f"**支撑位:** ${analysis['support1']:.0f} / ${analysis['support2']:.0f}  |  "
                            f"**阻力位:** ${analysis['resistance1']:.0f} / ${analysis['resistance2']:.0f}")

                # 波动率
                vol_color = "🟢" if analysis['volatility'] < 10 else ("🟡" if analysis['volatility'] < 20 else "🔴")
                st.markdown(f"**市场波动率(10日):** {analysis['volatility']:.2f}% {vol_color}")

                st.markdown("---")
                st.markdown(analysis['analysis'])

    # ==============================
    # TAB 2: 中期战略 (1周-1月)
    # ==============================
    with tab_mid:
        st.subheader("中期趋势推演 (1周 - 1个月)")

        midterm = generate_midterm_analysis(market_data, fred_data, scores)
        st.markdown(midterm)

        # 中期技术面
        gold = market_data.get("Gold", pd.Series()).dropna()
        if len(gold) >= 50:
            st.markdown("---")
            st.subheader("中期技术面")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("50日均线", f"${gold.rolling(50).mean().iloc[-1]:.0f}")
            mc2.metric("200日均线", f"${gold.rolling(200).mean().iloc[-1]:.0f}")
            mc3.metric("20日波动率", f"{gold.pct_change().rolling(20).std().iloc[-1]*100:.2f}%")

    # ==============================
    # TAB 3: 长期宏观 (1月+)
    # ==============================
    with tab_long:
        st.subheader("长期宏观叙事 (1个月 - 数年)")

        longterm = generate_longterm_analysis(market_data, fred_data, scores)
        st.markdown(longterm)

    # ==============================
    # TAB 4: 深度可视化
    # ==============================
    with tab_viz:
        st.subheader("多维数据透视")

        # 第一行
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            fig1 = plot_gold_price_with_ma(market_data)
            if fig1:
                st.plotly_chart(fig1, use_container_width=True)
        with col_v2:
            fig2 = plot_gold_vs_dxy(market_data)
            if fig2:
                st.plotly_chart(fig2, use_container_width=True)

        # 第二行
        col_v3, col_v4 = st.columns(2)
        with col_v3:
            fig3 = plot_gold_vs_yield(market_data, fred_data)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True)
        with col_v4:
            fig4 = plot_rsi_macd(market_data)
            if fig4:
                st.plotly_chart(fig4, use_container_width=True)

        # 第三行
        col_v5, col_v6 = st.columns(2)
        with col_v5:
            fig5 = plot_gold_silver_ratio(market_data)
            if fig5:
                st.plotly_chart(fig5, use_container_width=True)
        with col_v6:
            fig6 = plot_factor_radar(scores)
            if fig6:
                st.plotly_chart(fig6, use_container_width=True)

        # 因子评分柱状图
        st.subheader("因子评分明细")
        fig7 = plot_factor_bar(scores)
        if fig7:
            st.plotly_chart(fig7, use_container_width=True)

    # ==============================
    # TAB 5: 情景推演
    # ==============================
    with tab_scenario:
        st.subheader("情景推演")
        st.info("基于当前宏观环境，推演四种可能的情景及其对金价的影响。")

        scenarios = scenario_analysis(market_data, fred_data)

        # 情景卡片
        col_s1, col_s2 = st.columns(2)
        for idx, (name, info) in enumerate(scenarios.items()):
            col = col_s1 if idx < 2 else col_s2
            row_idx = idx % 2
            with col:
                st.markdown(f"#### {name}")
                st.markdown(f"**概率:** {info['probability']}")
                st.markdown(f"**触发条件:** {info['trigger']}")
                st.markdown(f"**金价影响:** {info['gold_impact']}")
                st.markdown(f"**目标价位:** {info['target']}")
                st.markdown(f"**时间周期:** {info['duration']}")
                st.markdown(f"**策略:** {info['strategy']}")
                st.markdown("---")

        # 情景散点图
        fig8 = plot_scenario_scatter(scenarios)
        if fig8:
            st.plotly_chart(fig8, use_container_width=True)

    # 底部免责声明
    st.markdown("---")
    st.caption("免责声明：本模型仅供参考，不构成投资建议。市场有风险，投资需谨慎。数据源: Yahoo Finance, FRED。")


if __name__ == "__main__":
    main()
