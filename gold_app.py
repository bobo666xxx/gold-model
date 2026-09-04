import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fredapi import Fred

# =========================
# 配置
# =========================
FRED_API_KEY = st.secrets["FRED_API_KEY"]  # ← 替换成你自己的

# 更新权重方案，加入新因子
WEIGHT_GRID = {
    "均衡权重": {
        "real_rate": -0.20,
        "usd": -0.15,
        "inflation": 0.10,
        "employment": 0.05,
        "economic_activity": 0.05,
        "market_sentiment": 0.15,
        "central_bank": 0.20,  # 央行购金
        "fiscal_deficit": 0.20, # 财政赤字
    },
    "宏观债务主导": {
        "real_rate": -0.15,
        "usd": -0.10,
        "inflation": 0.10,
        "employment": 0.05,
        "economic_activity": 0.05,
        "market_sentiment": 0.10,
        "central_bank": 0.20,
        "fiscal_deficit": 0.45, # 极度看重债务问题
    },
    "传统宏观主导": {
        "real_rate": -0.40,
        "usd": -0.30,
        "inflation": 0.15,
        "employment": 0.05,
        "economic_activity": 0.05,
        "market_sentiment": 0.05,
        "central_bank": 0.00,
        "fiscal_deficit": 0.00,
    },
}

# =========================
# 数据获取
# =========================
@st.cache_data(ttl=3600)
def fetch_all_data(api_key: str) -> pd.DataFrame:
    fred = Fred(api_key=api_key)
    series_map = {
        "gold": "GOLDAMGBD228NLBM",
        "real_rate": "REAINTRATREARAT10Y",
        "usd": "DTWEXBGS",
        "cpi": "CPIAUCSL",
        "unemployment": "UNRATE",
        "nonfarm": "PAYEMS",
        "gdp": "GDP",
        "vix": "VIXCLS",
        # 新增因子代码
        "central_bank_gold": "WOGOLD", # 全球央行黄金储备 (吨)
        "fiscal_deficit": "FYFSD",     # 美国财政赤字 (十亿美元，负值表示赤字)
    }
    frames = {}
    for name, sid in series_map.items():
        try:
            s = fred.get_series(sid)
            s.name = name
            frames[name] = s
        except Exception as e:
            st.warning(f"获取 {name} 失败: {e}")
    
    # 合并数据，按日期对齐
    df = pd.concat(frames.values(), axis=1).dropna()
    return df

# =========================
# 因子计算
# =========================
def compute_factors(df: pd.DataFrame) -> pd.DataFrame:
    factors = pd.DataFrame(index=df.index)
    
    # 1. 传统因子
    factors["real_rate"] = -df["real_rate"] # 实际利率反向
    factors["usd"] = -df["usd"].pct_change(60) # 美元60日跌幅
    factors["inflation"] = df["cpi"].pct_change(12) # 通胀同比
    factors["employment"] = -df["unemployment"].diff() + df["nonfarm"].pct_change() # 就业恶化程度
    factors["economic_activity"] = df["gdp"].pct_change(4) # GDP增速
    factors["market_sentiment"] = -df["vix"].pct_change(20) # 恐慌指数变化（通常VIX涨利好黄金，但这里取变化率平滑）
    
    # 2. 新增因子
    # 央行购金：计算同比变化率，购金增加利好黄金
    factors["central_bank"] = df["central_bank_gold"].pct_change(12)
    
    # 财政赤字：FRED数据中FYFSD通常是负数表示赤字。
    # 逻辑：赤字扩大（数值更负）-> 利好黄金。
    # 处理：取相反数，使赤字扩大时因子值为正。
    factors["fiscal_deficit"] = -df["fiscal_deficit"].pct_change(4) # 4季度变化率
    
    return factors.dropna()

def zscore(s: pd.Series, window: int = 180) -> pd.Series:
    return (s - s.rolling(window, min_periods=24).mean()) / s.rolling(window, min_periods=24).std()

def build_signal(factors: pd.DataFrame, weights: dict, window: int = 180) -> pd.DataFrame:
    z = factors.apply(zscore, window=window)
    # 确保权重字典只包含因子中存在的列
    valid_weights = {k: v for k, v in weights.items() if k in z.columns}
    score = sum(z[k] * v for k, v in valid_weights.items())
    
    out = factors[["gold"]].copy()
    out["gold_ret"] = out["gold"].pct_change()
    out["score"] = score
    return out.dropna()

# =========================
# 回测引擎
# =========================
def simple_backtest(base: pd.DataFrame, threshold: float = 0.5):
    sig = np.where(base["score"] > threshold, 1, np.where(base["score"] < -threshold, -1, 0))
    pos = pd.Series(sig, index=base.index).replace(0, method="ffill").fillna(0)
    strat_ret = pos.shift(1) * base["gold_ret"]
    equity = (1 + strat_ret).cumprod()
    trades = strat_ret[strat_ret != 0]
    return {"equity": equity, "trades": trades, "positions": pos}

def calc_metrics(equity: pd.Series, trades: pd.Series):
    total_ret = equity.iloc[-1] / equity.iloc[0] - 1
    sharpe = trades.mean() / trades.std() * np.sqrt(252) if trades.std() > 0 else 0
    max_dd = (equity / equity.cummax() - 1).min()
    win_rate = (trades > 0).mean() if len(trades) > 0 else 0
    return {"累计收益": total_ret, "Sharpe": sharpe, "最大回撤": max_dd, "胜率": win_rate}

# =========================
# 智能分析报告生成器
# =========================
def generate_analysis_report(base: pd.DataFrame, metrics: dict, weights: dict):
    if base.empty or not metrics:
        return "数据不足，无法生成分析报告。"

    latest_score = base["score"].iloc[-1]
    latest_date = base.index[-1].strftime("%Y-%m-%d")
    latest_gold = base["gold"].iloc[-1]

    # 1. 趋势诊断
    if latest_score > 1.0:
        trend = "🔥 **强势多头趋势**"
        trend_desc = "综合得分显著高于历史均值，宏观与新因子共振强烈支撑黄金。"
    elif latest_score > 0.5:
        trend = "📈 **温和偏多趋势**"
        trend_desc = "综合得分处于偏多区间，具备上行动能。"
    elif latest_score > -0.5:
        trend = "⚖️ **中性震荡趋势"
        trend_desc = "多空力量均衡，可能维持区间震荡。"
    elif latest_score > -1.0:
        trend = "📉 **温和偏空趋势**"
        trend_desc = "综合得分处于偏空区间，宏观环境形成压制。"
    else:
        trend = "❄️ **强势空头趋势**"
        trend_desc = "综合得分极低，市场情绪悲观或实际利率大幅走高。"

    # 2. 核心驱动因子分析
    # 重新计算Z-score用于解释
    factors_only = base.drop(columns=["gold", "gold_ret", "score"])
    z = (factors_only - factors_only.rolling(180, min_periods=24).mean()) / factors_only.rolling(180, min_periods=24).std()
    
    latest_z = z.iloc[-1]
    valid_weights = {k: v for k, v in weights.items() if k in latest_z.index}
    contributions = latest_z * pd.Series(valid_weights)
    
    top_positive = contributions.nlargest(2)
    top_negative = contributions.nsmallest(2)

    driver_analysis = "**主要多头贡献：**\n"
    has_pos = False
    for factor, val in top_positive.items():
        if val > 0:
            driver_analysis += f"- 🟢 **{factor}** (贡献度: +{val:.3f})\n"
            has_pos = True
    if not has_pos: driver_analysis += "- 无明显正向驱动\n"

    driver_analysis += "\n**主要空头拖累：**\n"
    has_neg = False
    for factor, val in top_negative.items():
        if val < 0:
            driver_analysis += f"- 🔴 **{factor}** (贡献度: {val:.3f})\n"
            has_neg = True
    if not has_neg: driver_analysis += "- 无明显负向拖累\n"

    # 3. 策略表现评估
    sharpe = metrics.get("Sharpe", 0)
    max_dd = metrics.get("最大回撤", 0)

    if sharpe > 1.5 and max_dd > -0.15:
        strategy_rating = "🌟 **优秀**：风险收益比极佳。"
    elif sharpe > 0.8:
        strategy_rating = "👍 **良好**：表现稳健。"
    elif sharpe > 0:
        strategy_rating = "⚠️ **一般**：收益勉强覆盖风险。"
    else:
        strategy_rating = "❌ **较差**：策略失效。"

    # 4. 综合建议
    if latest_score > 0.5 and sharpe > 0.8:
        advice = "💡 **操作参考**：趋势向上且策略有效，可考虑逢低做多。"
    elif latest_score < -0.5:
        advice = "💡 **操作参考**：趋势向下，建议规避多头风险。"
    else:
        advice = "💡 **操作参考**：信号不明确，建议观望。"

    report = f"""
### 📊 黄金多因子智能分析报告 ({latest_date})

**1. 市场趋势诊断**
- **当前状态**：{trend}
- **状态解析**：{trend_desc}
- **最新金价**：${latest_gold:.2f} | **综合得分**：{latest_score:.3f}

**2. 核心驱动因子分析**
{driver_analysis}

**3. 历史回测策略评估**
- **累计收益**：{metrics.get('累计收益', 0):.2%} | **胜率**：{metrics.get('胜率', 0):.2%}
- **策略评级**：{strategy_rating}

**4. 综合操作建议**
{advice}

> ⚠️ *免责声明：本报告由量化模型自动生成，仅供研究参考。*
"""
    return report

# =========================
# 绘图
# =========================
def plot_signal(base: pd.DataFrame):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(base.index, base["gold"], color="gold", linewidth=1.5)
    axes[0].set_title("Gold Price", color="white")
    axes[0].set_facecolor("#1a1a2e")
    axes[0].tick_params(colors="white")
    
    axes[1].plot(base.index, base["score"], color="cyan", linewidth=1.2)
    axes[1].axhline(0.5, color="lime", ls="--", lw=0.8)
    axes[1].axhline(-0.5, color="red", ls="--", lw=0.8)
    axes[1].fill_between(base.index, base["score"], 0, where=base["score"] > 0, alpha=0.3, color="lime")
    axes[1].fill_between(base.index, base["score"], 0, where=base["score"] < 0, alpha=0.3, color="red")
    axes[1].set_title("Composite Score", color="white")
    axes[1].set_facecolor("#1a1a2e")
    axes[1].tick_params(colors="white")
    
    fig.patch.set_facecolor("#0e1117")
    plt.tight_layout()
    return fig

def plot_backtest(result: dict):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(result["equity"].index, result["equity"], color="lime", linewidth=1.5)
    axes[0].set_title("Equity Curve", color="white")
    axes[0].set_facecolor("#1a1a2e")
    axes[0].tick_params(colors="white")
    
    dd = result["equity"] / result["equity"].cummax() - 1
    axes[1].fill_between(dd.index, dd, 0, color="red", alpha=0.5)
    axes[1].set_title("Drawdown", color="white")
    axes[1].set_facecolor("#1a1a2e")
    axes[1].tick_params(colors="white")
    
    fig.patch.set_facecolor("#0e1117")
    plt.tight_layout()
    return fig

# =========================
# 主程序
# =========================
def main():
    st.set_page_config(page_title="Gold Factor Model Pro", layout="wide")
    st.title("🏆 黄金多因子量化分析系统 (含央行与赤字因子)")

    with st.sidebar:
        st.header("参数设置")
        api_key = st.text_input("FRED API Key", value=FRED_API_KEY, type="password")
        weight_scheme = st.selectbox("权重方案", list(WEIGHT_GRID.keys()))
        threshold = st.slider("信号阈值", -1.0, 1.0, 0.5, 0.1)
        run = st.button("🚀 运行分析", type="primary")

    if run and api_key:
        with st.spinner("正在获取数据并计算..."):
            raw = fetch_all_data(api_key)
            factors = compute_factors(raw)
            weights = WEIGHT_GRID[weight_scheme]
            base = build_signal(factors, weights)
            result = simple_backtest(base, threshold)
            metrics = calc_metrics(result["equity"], result["trades"])
            st.session_state.update({
                "base": base, "result": result,
                "metrics": metrics, "weights": weights,
            })

    if "base" in st.session_state:
        base = st.session_state["base"]
        metrics = st.session_state["metrics"]
        weights = st.session_state["weights"]
        latest_score = base["score"].iloc[-1]
        signal_text = "🟢 偏多" if latest_score > threshold else "🔴 偏空" if latest_score < -threshold else "⚪ 中性"

        # 指标卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("综合得分", f"{latest_score:.3f}")
        col2.metric("信号方向", signal_text)
        col3.metric("最新金价", f"${base['gold'].iloc[-1]:.2f}")
        col4.metric("Sharpe", f"{metrics['Sharpe']:.2f}")

        # 智能分析报告
        st.markdown("---")
        report_text = generate_analysis_report(base, metrics, weights)
        st.markdown(report_text)

        # 图表
        st.markdown("---")
        st.subheader("信号走势图")
        fig_signal = plot_signal(base)
        st.pyplot(fig_signal)

        st.subheader("回测净值与回撤")
        fig_bt = plot_backtest(st.session_state["result"])
        st.pyplot(fig_bt)

        # 回测指标表
        st.subheader("回测指标")
        st.dataframe(pd.DataFrame([metrics]).T.rename(columns={0: "数值"}))

if __name__ == "__main__":
    main()
