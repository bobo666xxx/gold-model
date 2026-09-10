import akshare as ak
import streamlit as st
import pandas as pd

# 设置缓存，每60秒自动刷新一次数据，避免频繁请求导致卡顿
@st.cache_data(ttl=60)
def fetch_realtime_gold_data():
    """一键抓取国际和国内黄金实时行情"""
    try:
        # 1. 获取伦敦金（国际现货黄金）实时行情
        international_df = ak.futures_foreign_commodity_realtime(symbol="XAU")
        
        # 2. 获取国内上期所黄金主力合约（代替国内现货/期货）
        domestic_df = ak.futures_zh_spot(symbol="au0", market="SHFE", adjust='F')
        
        return international_df, domestic_df
    except Exception as e:
        st.error(f"自动抓取数据失败，请检查网络或稍后重试：{e}")
        return None, None

# --- 在你的 Streamlit 页面渲染区域调用 ---
st.subheader("📈 实时金价数据看板")

intl_data, dom_data = fetch_realtime_gold_data()

if intl_data is not None and not intl_data.empty:
    # 展示国际金价（伦敦金）
    st.success(f"✅ 国际金价 (伦敦金) 抓取成功！最新报价: {intl_data['最新价'].values[0]} 美元/盎司")
    st.dataframe(intl_data, use_container_width=True)

if dom_data is not None and not dom_data.empty:
    # 展示国内金价（上海期货交易所黄金主力合约）
    st.success(f"✅ 国内金价 (上期所主力合约) 抓取成功！最新报价: {dom_data['最新价'].values[0]} 元/克")
    st.dataframe(dom_data, use_container_width=True)
