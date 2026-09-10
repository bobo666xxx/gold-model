import streamlit as st
import pandas as pd
import requests

# 设置页面配置
st.set_page_config(page_title="实时金价数据看板", layout="centered")
st.title("📈 实时金价数据看板")

# 缓存机制：每300秒（5分钟）刷新一次，既保证时效性，又避免请求太快被封
@st.cache_data(ttl=300)
def fetch_gold_prices():
    """通过全球稳定API获取国际金价和美元汇率"""
    try:
        # 1. 获取国际现货黄金实时价格 (美元/盎司)
        # 使用全球通用的贵金属数据源
        gold_url = "https://data-asg.goldprice.org/dbXRates/USD"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
        }
        gold_response = requests.get(gold_url, headers=headers, timeout=10)
        gold_data = gold_response.json()
        international_price_usd = gold_data['items'][0]['xauPrice'] # 美元/盎司
        
        # 2. 获取最新的美元兑人民币汇率
        exchange_url = "https://open.er-api.com/v6/latest/USD"
        exchange_response = requests.get(exchange_url, timeout=10)
        exchange_data = exchange_response.json()
        usd_cny_rate = exchange_data['rates']['CNY']
        
        return international_price_usd, usd_cny_rate
    
    except Exception as e:
        # 如果获取失败，返回 None，由主程序展示提示
        return None, None

# --- 页面主逻辑 ---
intl_price, rate = fetch_gold_prices()

# 检查数据是否获取成功
if intl_price is None or rate is None:
    st.error("❌ 数据获取超时！")
    st.info("由于当前应用运行在海外服务器，连接国内数据源被拦截，同时国际数据源也可能临时拥堵。请刷新页面重试。")
else:
    # 1. 展示国际金价
    st.metric(label="🌍 国际现货黄金 (美元/盎司)", value=f"${intl_price:,.2f}")
    
    # 2. 实时换算国内金价
    # 换算公式：(美元/盎司) * 汇率(美元兑人民币) / 31.1035(盎司转克)
    domestic_price = (intl_price * rate) / 31.1035
    st.metric(label="🇨🇳 实时国内金价 (人民币/克)", value=f"¥{domestic_price:,.2f}")
    
    st.success("✅ 数据已实时更新！")
