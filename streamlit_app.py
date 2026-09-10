import akshare as ak
import streamlit as st
import pandas as pd

# 设置应用标题
st.set_page_config(page_title="实时金价看板", layout="centered")
st.title("📈 实时金价数据看板")

# 使用缓存，每60秒自动刷新一次数据，避免频繁请求导致卡顿或IP被限
@st.cache_data(ttl=60)
def fetch_realtime_gold_data():
    """一键抓取国际和国内黄金实时行情"""
    try:
        # 1. 获取国内上期所黄金主力合约 (如 au2612) 的实时行情
        domestic_df = ak.futures_zh_realtime(symbol="au0")
        
        # 2. 获取国际现货黄金 (伦敦金 XAU) 的实时行情
        international_df = ak.futures_zh_realtime(symbol="XAU")
        
        return domestic_df, international_df
    except Exception as e:
        st.error(f"自动抓取数据失败，请检查网络或稍后重试：{e}")
        return None, None

# --- 页面显示逻辑 ---
dom_data, intl_data = fetch_realtime_gold_data()

# 如果成功获取数据，展示在界面上
if dom_data is not None and intl_data is not None:
    st.success("✅ 实时数据获取成功！")
    
    st.subheader("🇨🇳 国内黄金主力合约 (上期所)")
    st.dataframe(dom_data, use_container_width=True)
    
    st.subheader("🌍 国际现货黄金 (伦敦金)")
    st.dataframe(intl_data, use_container_width=True)
else:
    st.warning("⚠️ 暂时无法获取行情数据，请稍后重试。")
