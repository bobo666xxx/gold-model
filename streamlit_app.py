import akshare as ak
import streamlit as st
import pandas as pd

# 设置页面配置
st.set_page_config(page_title="实时金价看板", layout="centered")
st.title("📈 实时金价数据看板")

# 缓存60秒，防止刷新太快导致IP被限
@st.cache_data(ttl=60)
def fetch_realtime_gold_data():
    try:
        # 1. 获取国内上期所黄金主力合约实时行情
        # 使用目前最稳定的期货实时接口，直接指定当前主力合约 au2612
        domestic_df = ak.futures_zh_spot(symbol="au2612", adjust="0", period="symbol")
        
        # 2. 获取国际现货黄金（伦敦金 XAU）实时行情
        # 使用新浪财经的期货接口，symbol 格式为 "XAU" 或 "XAUUSD"
        international_df = ak.futures_foreign_hist(symbol="XAU")
        # 取最新的一条数据作为实时行情
        if not international_df.empty:
            international_df = international_df.iloc[[-1]]
        
        return domestic_df, international_df
    except Exception as e:
        # 将错误打印到控制台，方便排查（Streamlit Cloud 可以在 Manage app -> Logs 查看）
        print(f"抓取国内黄金数据报错: {e}")
        print(f"抓取国际黄金数据报错: {e}")
        return None, None

# --- 页面显示逻辑 ---
dom_data, intl_data = fetch_realtime_gold_data()

# 显示国内黄金数据
if dom_data is not None and not dom_data.empty:
    st.subheader("🇨🇳 国内黄金 (上期所 AU2612)")
    st.dataframe(dom_data, use_container_width=True)
else:
    st.warning("⚠️ 暂时无法获取国内行情数据，请稍后重试。")

# 显示国际黄金数据
if intl_data is not None and not intl_data.empty:
    st.subheader("🌍 国际现货黄金 (伦敦金 XAU)")
    st.dataframe(intl_data, use_container_width=True)
else:
    st.warning("⚠️ 暂时无法获取国际行情数据，请稍后重试。")
