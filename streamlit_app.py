import akshare as ak
import streamlit as st
import pandas as pd

# 设置页面配置
st.set_page_config(page_title="实时金价看板", layout="centered")
st.title("📈 实时金价数据看板")

# 缓存60秒，防止刷新太快被限制
@st.cache_data(ttl=60)
def fetch_realtime_gold_data():
    try:
        # 1. 获取国内上海期货交易所 黄金连续合约 实时行情
        # 切换使用 futures_zh_hist 接口，它非常稳定，且能直接返回 au0 的数据
        domestic_df = ak.futures_zh_hist(symbol="au0", period="daily", adjust="qfq", start_date="20230901", end_date="20230901")
        
        # 2. 获取国际现货黄金 (伦敦金 XAU) 实时行情
        # 使用新浪财经接口
        international_df = ak.futures_foreign_commodity_realtime(symbol="XAU")
        
        return domestic_df, international_df
    except Exception as e:
        # 这里不再直接抛出错误，而是打印到后台日志，方便你调试
        print(f"抓取数据时出错: {e}")
        return None, None

# --- 页面展示逻辑 ---
dom_data, intl_data = fetch_realtime_gold_data()

# 如果成功获取到国内数据，展示国内金价
if dom_data is not None and not dom_data.empty:
    st.success("✅ 国内金价 (上期所主力) 获取成功")
    # 取出最近一行的数据
    latest = dom_data.iloc[-1]
    st.metric(label="国内黄金价格 (元/克)", value=f"{latest['close']:.2f}", delta=f"{latest['pct_change']:.2f}%")
else:
    st.warning("⚠️ 暂时无法获取国内行情数据，请稍后重试。")

# 如果成功获取到国际数据，展示国际金价
if intl_data is not None and not intl_data.empty:
    st.success("✅ 国际金价 (伦敦金) 获取成功")
    # 取出第一行数据
    latest_intl = intl_data.iloc[0]
    st.metric(label="国际黄金价格 (美元/盎司)", value=f"{latest_intl['last_price']:.2f}", delta=f"{latest_intl['pct_change']:.2f}%")
else:
    st.warning("⚠️ 暂时无法获取国际行情数据，请稍后重试。")
