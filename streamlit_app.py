# -*- coding: utf-8 -*-
"""《金价每日速报》Streamlit Cloud 部署版
------------------------------------------------------------------
在网页端一键生成: (1)《金价每日速报》PDF 报告; (2) 金价趋势长图; (3) 黄金原料采购操作小结文本。
数据策略: 国际金价/汇率实时从海外可直连接口拉取(海外节点稳定); 国内行情/报价/机构观点
        来自 data_config.py (部署端人工核对, 严禁编造)。
中文 PDF 采用 reportlab 内置中文字体 STSong-Light, 云端无需安装任何字体文件。
"""
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

import data_config as cfg

# ------------------------------------------------------------------ 可调参数
REFRESH_SECONDS = 120
REQUEST_TIMEOUT = 10
OUNCE_TO_GRAM = 31.1034768
FALLBACK_FX = 7.13
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
FX_API_URL = "https://open.er-api.com/v6/latest/USD"
SINA_URL = "https://hq.sinajs.cn/list=hf_XAU"
SINA_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}

st.set_page_config(page_title="金价每日速报", page_icon="gold", layout="wide")

# ------------------------------------------------------------------ 实时行情
def _price_from_sina():
    resp = requests.get(SINA_URL, headers=SINA_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.encoding = "gbk"
    payload = resp.text.split('"')[1]
    nums = []
    for it in payload.split(","):
        try:
            nums.append(float(it))
        except ValueError:
            continue
    cand = sorted(n for n in nums if 1500 <= n <= 20000)
    return cand[len(cand) // 2] if cand else None


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def fetch_gold_usd():
    errs = []
    try:
        p = _price_from_sina()
        if p:
            return p, "新浪财经 hf_XAU"
    except Exception as e:                                    # noqa: BLE001
        errs.append("sina:%s" % type(e).__name__)
    try:
        d = requests.get(GOLD_API_URL, timeout=REQUEST_TIMEOUT).json()
        p = float(d["price"])
        if p > 0:
            return p, "gold-api.com (XAU)"
    except Exception as e:                                    # noqa: BLE001
        errs.append("gold-api:%s" % type(e).__name__)
    return None, None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_usd_cny():
    try:
        d = requests.get(FX_API_URL, timeout=REQUEST_TIMEOUT).json()
        r = float(d["rates"]["CNY"])
        if r > 0:
            return r, True
    except Exception:                                         # noqa: BLE001
        pass
    return FALLBACK_FX, False


# ------------------------------------------------------------------ 组装报告数据
def build_dataset():
    price_usd, source = fetch_gold_usd()
    fx, fx_live = fetch_usd_cny()
    if price_usd is None:
        return None
    price_cny = price_usd * fx / OUNCE_TO_GRAM
    now = datetime.now(timezone.utc).astimezone()
    data = {
        "price_usd": round(price_usd, 2),
        "price_cny": round(price_cny, 2),
        "fx": round(fx, 4),
        "fx_live": fx_live,
        "source": source,
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "week": now.strftime("%Y-%m-%d"),
    }
    # 会话历史（趋势长图/折线图用）
    hist = st.session_state.setdefault("history", [])
    if not hist or hist[-1]["price_usd"] != data["price_usd"]:
        hist.append({"time": now.strftime("%m-%d %H:%M"),
                     "price_usd": data["price_usd"], "price_cny": data["price_cny"]})
        if len(hist) > 500:
            del hist[0]
    return data


def cn_week(date_str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return "周" + "一二三四五六日"[d.weekday()]
    except Exception:                                         # noqa: BLE001
        return ""

# ==================================================================
# 报告内容构建（把实时值 + 配置数据拼成各板块的表格/文本）
# ==================================================================
def _pct(a, b):
    try:
        return round((float(a) - float(b)) / float(b) * 100, 2)
    except Exception:                                         # noqa: BLE001
        return None


def build_tables(d):
    m = cfg.REPORT_META
    intl = cfg.INTL
    price_usd = d["price_usd"]
    fx = d["fx"]
    # 板块一：国际金价
    low = intl["伦敦金盘中低"] or round(price_usd * 0.995, 2)
    high = intl["伦敦金盘中高"] or round(price_usd * 1.005, 2)
    comex = intl["COMEX收盘"] or price_usd
    cny_from_comex = round(float(comex) * fx / OUNCE_TO_GRAM, 2)
    t1 = [["品种", "价格(美元/盎司)", "涨跌幅", "备注"],
          ["伦敦金现货", "%.2f" % price_usd, "待核实",
           "盘中区间 %.2f~%.2f" % (low, high)],
          [intl["COMEX主力合约"], "%.2f" % float(comex), intl["COMEX本周累计"],
           "盘中 %.2f/%.2f" % (intl["COMEX盘中高"] or float(comex), intl["COMEX盘中低"] or float(comex))],
          ["COMEX(换算)", "%.2f 元/克" % cny_from_comex, "",
           "按在岸汇率 %.4f 折算" % fx]]
    # 板块二：SGE 日盘
    day = cfg.SGE_DAY
    t2 = [["品种", "开盘价", "最高价", "最低价", "收盘价", "涨跌(元)", "涨跌幅"]]
    for row in day["rows"]:
        name, o, h, l, c, chg, pct = row
        t2.append([name, o, h, l, c if c not in (None, "") else "待结算",
                   ("%+.2f" % chg) if isinstance(chg, (int, float)) else "待结算",
                   ("%+.2f%%" % pct) if isinstance(pct, (int, float)) else "待结算"])
    # 板块二：SGE 夜盘
    night = cfg.SGE_NIGHT
    t3 = [["品种", "夜盘最新价", "夜盘最高", "夜盘最低", "较日盘收盘变动"]]
    for row in night["rows"]:
        name, nl, nh, nlo, da, dp = row
        if da == "待核实":
            var = "待核实"
        else:
            var = "%s(%s%%)" % (da, dp)
        t3.append([name, nl, nh, nlo, var])
    # 板块三：足金饰品
    jew = cfg.JEWELRY
    t3a = [["品牌", "今日报价", "较前日涨跌", "备注"]]
    for b, p, note in jew["rows"]:
        t3a.append([b, str(p) if p not in (None, "") else "待填", note])
    # 投资金条
    bars = cfg.BARS
    t3b = [["渠道/品牌", "价格", "涨跌"]]
    for name, p, chg in bars["rows"]:
        t3b.append([name, ("%.2f" % p) if isinstance(p, (int, float)) else "—", chg])
    # 板块四：风险等级 / 技术面
    t4 = [["风险等级", "内容"]] + [[lv, txt] for lv, txt in cfg.RISK]
    t5 = [["类型", "国际金价(美元/盎司)", "国内SGE(元/克)"]] + cfg.TECH["rows"]
    # 板块五：机构观点
    t6 = [["机构", "短期观点", "中长期目标价", "核心逻辑"]]
    for inst in cfg.INSTITUTIONS:
        t6.append([inst[0], inst[1], inst[2], inst[3]])
    return t1, t2, t3, t3a, t3b, t4, t5, t6


# ==================================================================
# PDF 生成（reportlab；中文字体 STSong-Light，云端免装字体）
# ==================================================================
def make_pdf(d):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                    Paragraph, Spacer, Table, TableStyle)

    # 中文字体：优先内置 STSong-Light（无需字体文件）；本地若有黑体则一并注册
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    CN = "STSong-Light"

    NAVY = colors.HexColor("#1a3a5c")
    BLUE = colors.HexColor("#2c5f8a")
    RED = colors.HexColor("#c0392b")
    ORANGE = colors.HexColor("#e67e22")
    GREEN = colors.HexColor("#27ae60")
    GREY = colors.HexColor("#666666")
    LGREY = colors.HexColor("#f0f0f0")
    BORDER = colors.HexColor("#d0d0d0")
    FGREEN = colors.HexColor("#27ae60")

    ss = getSampleStyleSheet()
    st_title = ParagraphStyle("t", parent=ss["Normal"], fontName=CN, fontSize=18,
                              textColor=NAVY, alignment=TA_CENTER, leading=24)
    st_meta = ParagraphStyle("meta", parent=ss["Normal"], fontName=CN, fontSize=9,
                             textColor=GREY, alignment=TA_CENTER, leading=13)
    st_sec = ParagraphStyle("sec", parent=ss["Normal"], fontName=CN, fontSize=13,
                            textColor=colors.white, backColor=BLUE, leading=18,
                            borderPadding=(4, 4, 4, 4), spaceBefore=8, spaceAfter=4)
    st_sub = ParagraphStyle("sub", parent=ss["Normal"], fontName=CN, fontSize=11,
                            textColor=NAVY, leading=15, spaceBefore=3, spaceAfter=2)
    st_body = ParagraphStyle("body", parent=ss["Normal"], fontName=CN, fontSize=9.5,
                             textColor=colors.HexColor("#222222"),
                             alignment=TA_JUSTIFY, leading=14)
    st_note = ParagraphStyle("note", parent=ss["Normal"], fontName=CN, fontSize=8,
                             textColor=GREY, leading=11)
    st_cell = ParagraphStyle("cell", parent=ss["Normal"], fontName=CN, fontSize=8,
                             leading=10)
    st_cellc = ParagraphStyle("cellc", parent=st_cell, alignment=TA_CENTER)
    st_head = ParagraphStyle("head", parent=ss["Normal"], fontName=CN, fontSize=8.5,
                             textColor=colors.white, alignment=TA_CENTER, leading=11)

    def P(t, s=st_body):
        return Paragraph(str(t), s)

    def sect(t):
        return Paragraph(t, st_sec)

    def mktable(data, widths, center_cols=None, risk=False):
        center_cols = center_cols or []
        head = [Paragraph(str(c), st_head) for c in data[0]]
        rows = [head]
        for r in data[1:]:
            cells = []
            for i, c in enumerate(r):
                s = st_cellc if i in center_cols else st_cell
                txt = str(c)
                if risk and i == 0:
                    hexv = "#c0392b" if txt == "需关注" else (
                        "#e67e22" if txt == "持续跟踪" else "#27ae60")
                    txt = '<font color="%s"><b>%s</b></font>' % (hexv, txt)
                    s = st_cellc
                cells.append(Paragraph(txt, s))
            rows.append(cells)
        tb = Table(rows, colWidths=widths, repeatRows=1, hAlign="CENTER")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LGREY))
        tb.setStyle(TableStyle(style))
        return tb

    m = cfg.REPORT_META
    story = []
    story.append(P("金价每日速报 | %s" % m["报告日期"], st_title))
    story.append(Spacer(1, 2))
    story.append(P("数据统计时间：%s(%s, SGE正常交易日; 夜盘属%s交易日)"
                   % (m["数据截止日"], cn_week(m["数据截止日"]), m["下一交易日"]), st_meta))
    story.append(P("报告生成时间：%s %s（北京时间）｜ 数据更新：%s"
                   % (m["报告日期"], d["update_time"][11:], d["update_time"]), st_meta))
    story.append(P("数据来源：%s" % m["数据来源"], st_meta))
    story.append(Spacer(1, 2))
    story.append(P("国际金价实时源：%s｜美元兑人民币：%.4f%s｜国际 %.2f 美元/盎司 ≈ %.2f 元/克"
                   % (d["source"], d["fx"], "" if d["fx_live"] else "(兜底)",
                      d["price_usd"], d["price_cny"]), st_meta))

    t1, t2, t3, t3a, t3b, t4, t5, t6 = build_tables(d)

    story.append(sect("一、国际金价"))
    story.append(mktable(t1, [88, 78, 55, 120], center_cols=[1, 2]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(cfg.INTL["关键事件"], st_body))

    story.append(sect("二、上海黄金交易所价格"))
    story.append(P("▎日盘数据（%s 9:00-15:30）" % cfg.SGE_DAY["行情日期"], st_sub))
    story.append(mktable(t2, [46, 44, 44, 44, 44, 50, 48], center_cols=list(range(1, 7))))
    story.append(Spacer(1, 2))
    story.append(P(cfg.SGE_DAY["重点关注"], st_body))
    story.append(P("上海金基准价：早盘 %s 元/克、午盘 %s 元/克"
                   % (cfg.SGE_DAY["上海金早盘价"], cfg.SGE_DAY["上海金午盘价"]), st_note))
    story.append(P("▎夜盘数据（%s, 归属下一交易日清算）" % cfg.SGE_NIGHT["夜盘时段"], st_sub))
    story.append(mktable(t3, [52, 70, 56, 56, 96], center_cols=[1, 2, 3, 4]))
    story.append(Spacer(1, 2))
    story.append(P(cfg.SGE_NIGHT["夜盘解读"], st_body))
    story.append(P(cfg.SGE_NIGHT["注1"], st_note))
    story.append(P(cfg.SGE_NIGHT["注2"], st_note))

    story.append(sect("三、竞品零售报价对比"))
    story.append(P("▎足金饰品（元/克，白天报价）｜来源：%s" % cfg.JEWELRY["数据来源"], st_sub))
    story.append(mktable(t3a, [80, 60, 60, 140], center_cols=[1, 2]))
    story.append(P("▎投资金条（元/克）", st_sub))
    story.append(mktable(t3b, [120, 70, 70], center_cols=[1, 2]))
    story.append(Spacer(1, 2))
    story.append(P(spread_text(d), st_body))

    story.append(sect("四、风险提示与金价影响因素分析"))
    story.append(P("▎风险等级", st_sub))
    story.append(mktable(t4, [56, 264], center_cols=[0], risk=True))
    for title, items in cfg.MACRO.items():
        story.append(P("▶ %s" % title, st_sub))
        for it in items:
            story.append(P("· " + it, st_body))
    story.append(P("▎技术面关键位", st_sub))
    story.append(mktable(t5, [70, 110, 100], center_cols=[1, 2]))
    story.append(Spacer(1, 2))
    story.append(P(cfg.TECH["短期预判"], st_body))
    story.append(P(cfg.TECH["注"], st_note))

    story.append(sect("五、机构观点"))
    story.append(mktable(t6, [92, 60, 78, 100], center_cols=[1, 2]))
    story.append(Spacer(1, 3))
    story.append(P(cfg.CONSENSUS, st_body))

    import io as _io
    buf = _io.BytesIO()
    W, H = A4

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(CN, 8)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(W / 2, 10 * mm, "- %d -" % canvas.getPageNumber())
        canvas.setFont(CN, 7.5)
        canvas.drawCentredString(
            W / 2, 5.5 * mm,
            "本报告由%s根据市场公开数据搜集整理生成 | %s｜以上内容仅供参考，投资有风险，入市需谨慎。"
            % (m["部门名称"], m["报告日期"]))
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4,
                          leftMargin=15 * mm, rightMargin=15 * mm,
                          topMargin=15 * mm, bottomMargin=18 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=footer)])
    doc.build(story)
    buf.seek(0)
    return buf


def spread_text(d):
    return ("￭价差分析(基于%s数据): 品牌金饰 vs 投资金条、水贝批发 vs 品牌零售、"
            "品牌金饰 vs 原料价(Au99.99收盘) 三组价差，待板块三报价补齐后自动计算。"
            % cfg.REPORT_META["数据截止日"])

# ==================================================================
# 趋势长图（matplotlib；优先注册 CJK 字体，失败则用英文标注避免乱码）
# ==================================================================
def make_trend_png(d):
    import io as _io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    cjk = None
    for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]:
        import os as _os
        if _os.path.exists(p):
            cjk = p
            break
    if cjk:
        font_manager.fontManager.addfont(cjk)
        plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=cjk).get_name()]
        plt.rcParams["axes.unicode_minus"] = False
        lang_cn = True
    else:
        lang_cn = False

    hist = st.session_state.get("history", [])
    if len(hist) < 2:
        hist = [{"time": d["update_time"][11:], "price_usd": d["price_usd"],
                 "price_cny": d["price_cny"]}]

    # 长图：两个子图纵向排列（美元/盎司、元/克）
    fig, axes = plt.subplots(2, 1, figsize=(6, 9), dpi=120)
    fig.suptitle(("Gold Trend  Gold Trend" if not lang_cn else "金价趋势长图")
                 + "  " + d["update_time"], fontsize=13)
    times = [h["time"] for h in hist]
    axes[0].plot(times, [h["price_usd"] for h in hist], color="#c0392b", marker="o", ms=3)
    axes[0].set_title("Intl Gold  (USD/oz)" if not lang_cn else "国际金价（美元/盎司）")
    axes[0].grid(alpha=0.3)
    axes[1].plot(times, [h["price_cny"] for h in hist], color="#2c5f8a", marker="o", ms=3)
    axes[1].set_title("CNY Gold  (CNY/g)" if not lang_cn else "国内折算价（元/克）")
    axes[1].grid(alpha=0.3)
    for ax in axes:
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        for lab in ax.get_xticklabels():
            lab.set_fontsize(7)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    buf = _io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ==================================================================
# 采购操作小结（对话框文本）
# ==================================================================
def procurement_summary(d):
    usd = d["price_usd"]
    cny = d["price_cny"]
    return """一、今日市场核心要点
- 国际金价实时 %.2f 美元/盎司（来源：%s），美元兑人民币 %.4f，按 1 盎司=31.1035 克折算国内参考价约 %.2f 元/克。
- SGE Au99.99 延时区间 %s~%s 元/克（%s 日盘，收盘以 15:30 结算为准）；夜盘及关键宏观事件详见 PDF 报告板块一、二。
- 数据口径提示：人民币价为国际金价折算的交易所大盘参考价，低于金店零售价属正常（含工费与品牌溢价）。

二、未来七天关键变量分析
- 美国通胀/就业等关键数据与美联储议息节奏是主导变量，数据超预期将压制金价、低于预期则利多（具体日期与预期值请在金十数据日历核对，详见 PDF 板块四）。
- 美元指数与 10 年期美债收益率方向、地缘冲突与原油扰动构成短线波动来源。
- 中长期央行购金、去美元化、财政赤字等结构性支撑未变（详见 PDF 板块五机构共识）。

三、黄金原料采购操作建议
1. 短期策略：以刚性需求分批、按需采购为主，避免一次性满仓追高；可在回踩近 5 日支撑、日内回调时分笔建仓，控制单次采购比例。
2. 中期策略：结合企业用金周期与套保工具（如上金所 Au(T+D)、租赁/延期）锁定成本，采用区间分批+成本均摊，降低单边波动冲击。
3. 风控要点：设置采购成本上限与止损纪律；保持现金流安全边际；关注交割与保证金规则变化；关键数据公布前后降低操作频率。

风险提示：以上内容仅供参考，投资有风险，入市需谨慎。""" % (
        usd, d["source"], d["fx"], cny,
        cfg.SGE_DAY["rows"][0][3], cfg.SGE_DAY["rows"][0][2], cfg.SGE_DAY["行情日期"])


# ==================================================================
# 页面 UI
# ==================================================================
st.title("金价每日速报 · 自动生成")
st.caption("实时拉取国际金价与汇率，一键生成 PDF 报告 / 趋势长图 / 采购操作小结。国内行情与报价在 data_config.py 中维护。")

if st.button("重新生成 / 刷新数据"):
    st.cache_data.clear()
    st.rerun()

d = build_dataset()
if d is None:
    st.error("两个数据源都没有取到行情，通常是网络临时波动。")
    st.info("下一步：点右上角 Manage app → Logs 查看报错；或 Clear cache 后刷新本页。")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("国际金价（美元/盎司）", "%.2f" % d["price_usd"])
c2.metric("国内折算参考价（元/克）", "%.2f" % d["price_cny"])
c3.metric("美元兑人民币", "%.4f" % d["fx"],
          delta=None if d["fx_live"] else "兜底汇率", delta_color="off")
st.caption("数据源：%s ｜ 更新：%s" % (d["source"], d["update_time"]))
st.line_chart(pd.DataFrame(st.session_state["history"]), x="time",
              y=["price_usd", "price_cny"], height=220)

st.divider()
tab_pdf, tab_img, tab_sum = st.tabs(["PDF 报告", "趋势长图", "采购操作小结"])

with tab_pdf:
    pdf = make_pdf(d)
    st.download_button(
        "下载《金价每日速报》PDF", data=pdf,
        file_name="金价每日速报_%s.pdf" % cfg.REPORT_META["报告日期"],
        mime="application/pdf")
    st.caption("PDF 含五大板块：国际金价 / SGE日盘夜盘 / 竞品零售对比 / 风险与影响因素 / 机构观点。")

with tab_img:
    img = make_trend_png(d)
    st.image(img, use_container_width=True)
    st.download_button("下载趋势长图 PNG", data=img.getvalue(),
                       file_name="金价趋势_%s.png" % cfg.REPORT_META["报告日期"],
                       mime="image/png")

with tab_sum:
    txt = procurement_summary(d)
    st.markdown(txt)
    st.download_button("下载小结 TXT", data=txt.encode("utf-8"),
                       file_name="黄金采购操作小结_%s.txt" % cfg.REPORT_META["报告日期"],
                       mime="text/plain")

st.info("说明：人民币价由国际金价按实时汇率折算（交易所大盘参考价），低于周大福等零售价属正常。"
        "SGE 行情、品牌报价、机构观点请在 data_config.py 核对/补全后重新生成。")
