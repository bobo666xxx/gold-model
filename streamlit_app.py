import akshare as ak
import streamlit as st
import pandas as pd

# 设置页面配置
st.set_page_config(page_title="实时金价看板", layout="centered")
st.title("📈 实时金价数据看板")

@st.cache_data(ttl=60)
def fetch_realtime_gold_data():
    """一键抓取国际和国内黄金实时行情"""
    try:
        # 1. 获取国内上期所黄金主力合约
        # 先获取主力合约代码映射表
        main_contracts = ak.futures_display_main_sina()
        # 筛选出上海期货交易所的黄金主力合约代码 (通常带 'AU' 且以 '0' 结尾代表主力连续)
        gold_main_code = main_contracts[main_contracts['symbol'].str.startswith('AU') & main_contracts['symbol'].str.endswith('0')]['symbol'].values[0]
        
        # 使用主力连续合约代码获取实时行情
        domestic_df = ak.futures_zh_realtime(symbol=gold_main_code)
        
        # 2. 获取国际现货黄金 (伦敦金 XAU) 的实时行情
        international_df = ak.futures_zh_realtime(symbol="XAU")
        
        return domestic_df, international_df
    except Exception as e:
        return None, None

# --- 页面显示逻辑 ---
dom_data, intl_data = fetch_realtime_gold_data()

# 如果成功获取数据，展示在界面上
if dom_data is not None and not dom_data.empty and intl_data is not None and not intl_data.empty:
    # 展示国际金价
    st.subheader("🌍 国际金价 (伦敦金 XAU)")
    st.dataframe(intl_data, use_container_width=True)
    
    st.divider()
    
    # 展示国内金价
    st.subheader(f"🇨🇳 国内金价 (主力合约)")
    st.dataframe(dom_data, use_container_width=True)
    
else:
    st.warning("⚠️ 暂时无法获取行情数据，请稍后重试。")
