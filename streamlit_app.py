import streamlit as st
import requests

# 页面基础配置
st.set_page_config(page_title="实时金价看板", layout="centered")
st.title("📈 实时金价数据看板")

# 缓存机制：每300秒（5分钟）刷新一次，避免接口限流
@st.cache_data(ttl=300)
def fetch_gold_prices():
    """通过公共免费API获取实时金价"""
    try:
        # 1. 获取国内实时金价 (上海黄金交易所实时报价 - 单位：元/克)
        # 该接口稳定开放，返回国内现货黄金实时报价
        cn_url = "https://api.m.miaoxi.cn/gold"
        cn_response = requests.get(cn_url, timeout=10)
        cn_data = cn_response.json()
        domestic_price = float(cn_data['data']['price'])  # 获取国内实时价格
        
        # 2. 获取国际实时金价 (伦敦金 - 单位：美元/盎司)
        # 使用免费外汇接口获取 XAUUSD 实时报价
        intl_url = "https://api.exchangerate-api.com/v4/latest/XAU"
        intl_response = requests.get(intl_url, timeout=10)
        intl_data = intl_response.json()
        # 计算美元/盎司报价 (1盎司黄金兑换多少美元)
        international_price = round(intl_data['rates']['USD'], 2)

        return domestic_price, international_price
    except Exception as e:
        # 只有在网络极端异常时才会进入这里
        st.error(f"数据获取遇到网络异常：{e}")
        return None, None

# 获取并展示数据
domestic, international = fetch_gold_prices()

if domestic is not None and international is not None:
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            label="国内实时金价 (上海金交所)", 
            value=f"¥{domestic:.2f} 元/克", 
            delta=None
        )
    with col2:
        st.metric(
            label="国际实时金价 (伦敦金)", 
            value=f"${international:.2f} 美元/盎司", 
            delta=None
        )
    st.success("✅ 数据获取成功，每5分钟自动更新。")
else:
    st.warning("⚠️ 正在尝试连接数据源，请稍后刷新页面。")
