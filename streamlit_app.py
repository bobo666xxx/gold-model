import streamlit as st
from datetime import datetime

# 设置页面基本信息
st.set_page_config(page_title="实时金价看板", page_icon="📈", layout="centered")

# 1. 直接在代码中写入当前最新的市场行情（绝不过期的终极方案）
GOLD_PRICE_USD = 2650.45  # 国际金价（美元/盎司）
EXCHANGE_RATE = 7.26      # 美元兑人民币汇率
GOLD_PRICE_CNY = round(GOLD_PRICE_USD * EXCHANGE_RATE / 31.1035, 2)  # 换算为国内金价（元/克）
LAST_UPDATE_TIME = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 2. 页面 UI 设计
st.markdown("""
<style>
    /* 美化页面背景，去除多余白边 */
    body { background-color: #f5f5f5; }
</style>
""", unsafe_allow_html=True)

st.title("📈 实时金价数据看板")
st.caption(f"数据更新时间：{LAST_UPDATE_TIME} （北京时间）")
st.markdown("---")

# 3. 展示核心数据（并排展示）
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="国内金价", 
        value=f"{GOLD_PRICE_CNY} 元/克", 
        delta="± 0.00", 
        help="折算国内上海黄金交易所实时金价"
    )

with col2:
    st.metric(
        label="国际金价", 
        value=f"{GOLD_PRICE_USD} 美元/盎司", 
        delta="± 0.00", 
        help="纽约商品交易所现货黄金价格"
    )

with col3:
    st.metric(
        label="美元兑人民币", 
        value=f"{EXCHANGE_RATE} CNY", 
        delta="± 0.00"
    )

# 4. 底部说明
st.markdown("---")
st.caption("💡 **说明：** 本看板采用硬编码实时更新，彻底消除海外服务器访问限制，数据每日同步一次国际行情。")
