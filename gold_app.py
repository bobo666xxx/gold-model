import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(page_title="黄金走势多因子分析模型", page_icon="", layout="wide")

# ============================================================
# 数据获取模块（全部免费，无需 API Key）
# ============================================================

@st.cache_data(ttl=300)
def fetch_market_data():
    """从 Yahoo Finance 获取市场数据"""
    try:
        tickers = {
            "gold": "GC=F",          # COMEX 黄金期货
            "dxy": "DX-Y.NYB",       # 美元指数
            "us10y": "^TNX",          # 美国10年期国债收益率
            "us2y": "^IRX",           # 美国短期国债收益率（近似）
            "sp500": "^GSPC",         # 标普500
            "vix": "^VIX",            # 恐慌指数
            "silver": "SI=F",         # 白银
            "oil": "CL=F",            # 原油
            "btc": "BTC-USD",         # 比特币（风险偏好参考）
        }
        data = {}
        for name, ticker in tickers.items():
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="6mo")
                if not hist.empty:
                    data[name] = hist
            except Exception:
                continue
        return data
    except Exception as e:
        st.error(f"数据获取异常: {e}")
        return {}


@st.cache_data(ttl=300)
def fetch_cpi_data():
    """从 FRED 公开页面获取 CPI 数据（无需 Key）"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        df['CPI_YoY'] = df['CPIAUCSL'].pct_change(12) * 100
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_unemployment_data():
    """从 FRED 获取失业率数据"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_fed_funds_rate():
    """获取联邦基金利率"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_nonfarm_payrolls():
    """获取非农就业数据"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=PAYEMS"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        df['NFP_Change'] = df['PAYEMS'].diff()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_retail_sales():
    """获取零售销售数据（消费指数代理）"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RSXFSN"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_industrial_production():
    """获取工业生产指数"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_us_debt():
    """获取美国国债总额"""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GFDEBTN"
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATE').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


# ============================================================
# 多因子评分引擎
# ============================================================

def calculate_factor_scores(market_data, cpi_df, unemp_df, fed_df, nfp_df, retail_df, indprod_df, debt_df):
    """计算各因子对黄金的评分（-100 到 +100，正=利多，负=利空）"""
    scores = {}
    details = {}

    # 1. 美元指数因子（负相关）
    if "dxy" in market_data and len(market_data["dxy"]) > 20:
        dxy = market_data["dxy"]["Close"]
        dxy_chg_1m = (dxy.iloc[-1] / dxy.iloc[-22] - 1) * 100 if len(dxy) > 22 else 0
        dxy_chg_3m = (dxy.iloc[-1] / dxy.iloc[-66] - 1) * 100 if len(dxy) > 66 else 0
        # 美元走弱利多黄金
        score = np.clip(-dxy_chg_1m * 15, -100, 100)
        scores["美元指数"] = score
        details["美元指数"] = f"1月变动: {dxy_chg_1m:+.2f}% | 3月变动: {dxy_chg_3m:+.2f}% | 当前: {dxy.iloc[-1]:.2f}"
    else:
        scores["美元指数"] = 0
        details["美元指数"] = "数据不可用"

    # 2. 实际利率因子（负相关）
    if "us10y" in market_data and len(cpi_df) > 0:
        us10y = market_data["us10y"]["Close"].iloc[-1]
        cpi_yoy = cpi_df["CPI_YoY"].dropna().iloc[-1] if not cpi_df["CPI_YoY"].dropna().empty else 3.0
        real_rate = us10y - cpi_yoy
        # 实际利率越低越利多黄金
        if real_rate < 0:
            score = np.clip(abs(real_rate) * 20, 0, 100)
        else:
            score = np.clip(-real_rate * 15, -100, 0)
        scores["实际利率"] = score
        details["实际利率"] = f"10Y国债: {us10y:.2f}% | CPI同比: {cpi_yoy:.2f}% | 实际利率: {real_rate:.2f}%"
    else:
        scores["实际利率"] = 0
        details["实际利率"] = "数据不可用"

    # 3. 通胀因子（正相关）
    if len(cpi_df) > 0:
        cpi_yoy = cpi_df["CPI_YoY"].dropna()
        if not cpi_yoy.empty:
            current_cpi = cpi_yoy.iloc[-1]
            cpi_trend = cpi_yoy.iloc[-1] - cpi_yoy.iloc[-2] if len(cpi_yoy) > 1 else 0
            # 通胀上升利多黄金
            score = np.clip((current_cpi - 2.0) * 25 + cpi_trend * 10, -100, 100)
            scores["通胀数据"] = score
            details["通胀数据"] = f"CPI同比: {current_cpi:.2f}% | 趋势: {'上升' if cpi_trend > 0 else '下降'}({cpi_trend:+.2f}%)"
        else:
            scores["通胀数据"] = 0
            details["通胀数据"] = "数据不足"
    else:
        scores["通胀数据"] = 0
        details["通胀数据"] = "数据不可用"

    # 4. 就业数据因子（非农低于预期利多黄金）
    if len(nfp_df) > 2:
        nfp_change = nfp_df["NFP_Change"].dropna()
        if not nfp_change.empty:
            latest_nfp = nfp_change.iloc[-1]
            avg_nfp = nfp_change.iloc[-12:].mean() if len(nfp_change) >= 12 else nfp_change.mean()
            deviation = latest_nfp - avg_nfp
            # 非农低于均值利多黄金（经济放缓→降息预期）
            score = np.clip(-deviation / 50, -100, 100)
            scores["就业数据"] = score
            details["就业数据"] = f"最新非农变动: {latest_nfp:+.0f}K | 12月均值: {avg_nfp:+.0f}K | 偏差: {deviation:+.0f}K"
        else:
            scores["就业数据"] = 0
            details["就业数据"] = "数据不足"
    else:
        scores["就业数据"] = 0
        details["就业数据"] = "数据不可用"

    # 5. 失业率因子（失业率上升利多黄金）
    if len(unemp_df) > 0:
        unemp = unemp_df["UNRATE"].dropna()
        if not unemp.empty:
            current_unemp = unemp.iloc[-1]
            unemp_chg = unemp.iloc[-1] - unemp.iloc[-2] if len(unemp) > 1 else 0
            # 失业率上升利多黄金
            score = np.clip((current_unemp - 3.5) * 30 + unemp_chg * 50, -100, 100)
            scores["失业率"] = score
            details["失业率"] = f"当前: {current_unemp:.1f}% | 变动: {unemp_chg:+.2f}%"
        else:
            scores["失业率"] = 0
            details["失业率"] = "数据不足"
    else:
        scores["失业率"] = 0
        details["失业率"] = "数据不可用"

    # 6. 美联储利率因子
    if len(fed_df) > 0:
        fed_rate = fed_df["FEDFUNDS"].dropna()
        if not fed_rate.empty:
            current_rate = fed_rate.iloc[-1]
            rate_chg = fed_rate.iloc[-1] - fed_rate.iloc[-2] if len(fed_rate) > 1 else 0
            # 降息周期利多黄金
            if rate_chg < 0:
                score = np.clip(abs(rate_chg) * 40, 0, 100)
            elif rate_chg > 0:
                score = np.clip(-abs(rate_chg) * 40, -100, 0)
            else:
                score = 20  # 维持不变偏中性偏多
            scores["美联储利率"] = score
            details["美联储利率"] = f"联邦基金利率: {current_rate:.2f}% | 最近变动: {rate_chg:+.2f}%"
        else:
            scores["美联储利率"] = 0
            details["美联储利率"] = "数据不足"
    else:
        scores["美联储利率"] = 0
        details["美联储利率"] = "数据不可用"

    # 7. 消费指数因子（消费疲软利多黄金）
    if len(retail_df) > 0:
        retail = retail_df["RSXFSN"].dropna()
        if len(retail) > 12:
            retail_chg = (retail.iloc[-1] / retail.iloc[-13] - 1) * 100
            # 消费疲软利多黄金
            score = np.clip(-retail_chg * 10, -100, 100)
            scores["消费指数"] = score
            details["消费指数"] = f"零售销售12月变动: {retail_chg:+.2f}%"
        else:
            scores["消费指数"] = 0
            details["消费指数"] = "数据不足"
    else:
        scores["消费指数"] = 0
        details["消费指数"] = "数据不可用"

    # 8. 工业生产指数因子
    if len(indprod_df) > 0:
        indprod = indprod_df["INDPRO"].dropna()
        if len(indprod) > 12:
            indprod_chg = (indprod.iloc[-1] / indprod.iloc[-13] - 1) * 100
            # 工业产出下降利多黄金（经济放缓）
            score = np.clip(-indprod_chg * 10, -100, 100)
            scores["生产指数"] = score
            details["生产指数"] = f"工业生产12月变动: {indprod_chg:+.2f}%"
        else:
            scores["生产指数"] = 0
            details["生产指数"] = "数据不足"
    else:
        scores["生产指数"] = 0
        details["生产指数"] = "数据不可用"

    # 9. VIX恐慌指数因子（正相关，避险）
    if "vix" in market_data and len(market_data["vix"]) > 5:
        vix = market_data["vix"]["Close"]
        current_vix = vix.iloc[-1]
        vix_avg = vix.iloc[-22:].mean() if len(vix) > 22 else vix.mean()
        # VIX高利多黄金
        score = np.clip((current_vix - 20) * 3, -100, 100)
        scores["地缘/避险(VIX)"] = score
        details["地缘/避险(VIX)"] = f"VIX当前: {current_vix:.1f} | 20日均值: {vix_avg:.1f}"
    else:
        scores["地缘/避险(VIX)"] = 0
        details["地缘/避险(VIX)"] = "数据不可用"

    # 10. 央行购金（基于黄金ETF资金流代理 + 金银比）
    if "gold" in market_data and "silver" in market_data:
        gold_price = market_data["gold"]["Close"].iloc[-1]
        silver_price = market_data["silver"]["Close"].iloc[-1]
        gold_silver_ratio = gold_price / silver_price if silver_price > 0 else 80
        # 金银比偏高说明避险需求强
        score = np.clip((gold_silver_ratio - 80) * 2, -100, 100)
        scores["央行购金/避险需求"] = score
        details["央行购金/避险需求"] = f"金银比: {gold_silver_ratio:.1f} | 黄金: ${gold_price:.2f} | 白银: ${silver_price:.2f}"
    else:
        scores["央行购金/避险需求"] = 0
        details["央行购金/避险需求"] = "数据不可用"

    # 11. 美国负债因子（正相关）
    if len(debt_df) > 0:
        debt = debt_df["GFDEBTN"].dropna()
        if len(debt) > 4:
            debt_latest = debt.iloc[-1]
            debt_chg = (debt.iloc[-1] / debt.iloc[-2] - 1) * 100 if len(debt) > 1 else 0
            # 债务持续增长利多黄金
            score = np.clip(debt_chg * 5 + 30, -100, 100)  # 基础偏多，因为美国债务长期增长
            scores["美国负债"] = score
            details["美国负债"] = f"国债总额: ${debt_latest/1e9:.0f}B | 季度变动: {debt_chg:+.2f}%"
        else:
            scores["美国负债"] = 0
            details["美国负债"] = "数据不足"
    else:
        scores["美国负债"] = 0
        details["美国负债"] = "数据不可用"

    return scores, details


def calculate_composite_score(scores):
    """计算加权综合评分"""
    weights = {
        "美元指数": 0.15,
        "实际利率": 0.18,
        "通胀数据": 0.12,
        "就业数据": 0.10,
        "失业率": 0.08,
        "美联储利率": 0.12,
        "消费指数": 0.05,
        "生产指数": 0.05,
        "地缘/避险(VIX)": 0.05,
        "央行购金/避险需求": 0.05,
        "美国负债": 0.05,
    }
    total_weight = 0
    weighted_sum = 0
    for factor, score in scores.items():
        w = weights.get(factor, 0.05)
        weighted_sum += score * w
        total_weight += w
    return weighted_sum / total_weight if total_weight > 0 else 0


def get_signal(composite_score):
    """根据综合评分给出信号"""
    if composite_score > 50:
        return "🟢 强烈看多", "green"
    elif composite_score > 20:
        return "🟢 偏多", "limegreen"
    elif composite_score > -20:
        return "🟡 中性震荡", "gold"
    elif composite_score > -50:
        return " 偏空", "orange"
    else:
        return " 强烈看空", "red"


def generate_report(scores, details, composite, signal, market_data):
    """生成分析报告"""
    report = []
    report.append("=" * 50)
    report.append(" 黄金走势多因子分析报告")
    report.append(f" 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append("=" * 50)
    report.append("")

    # 当前金价
    if "gold" in market_data:
        gold_price = market_data["gold"]["Close"].iloc[-1]
        gold_chg = (market_data["gold"]["Close"].iloc[-1] / market_data["gold"]["Close"].iloc[-2] - 1) * 100
        report.append(f" 当前金价: ${gold_price:.2f}/盎司 ({gold_chg:+.2f}%)")
    report.append(f" 综合评分: {composite:+.1f} / 100")
    report.append(f" 趋势信号: {signal}")
    report.append("")
    report.append("-" * 50)
    report.append(" 各因子评分明细:")
    report.append("-" * 50)

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for factor

[(doc_common_card_1)]
