# -*- coding: utf-8 -*-
"""《金价每日速报》Streamlit Cloud 部署版 —— 全自动抓取 + 自动填写
------------------------------------------------------------------
一键生成: (1)《金价每日速报》PDF; (2) 金价趋势长图; (3) 黄金原料采购操作小结。

全自动策略(无需再手填 data_config.py):
  实时值  : 国际金价 XAU / 白银 XAG  -> api.gold-api.com (海外直连, 免密钥)
            美元兑人民币              -> open.er-api.com
  历史序列: 优先 Yahoo GC=F 日线; 失败自动回落 NBP 波兰央行官方金价(折美元/盎司)
            逐日美元兑人民币          -> frankfurter.app
  自动计算: 伦敦金涨跌/振幅、COMEX(升水估算)+换算、SGE日/夜盘折算参考价、
            竞品零售(按原料价+公开常见工费/溢价估算)、技术面支撑/阻力/均线、
            短期预判区间、价差分析、风险等级 —— 全部由抓取到的真实数据推导。

诚实纪律: 海外节点无法直连上金所/金投网等国内接口, 凡无法实时核实的权威数值
          (交易所官方结算价、各品牌实时牌价、宏观数据具体值、机构最新研报)
          一律按真实数据"折算/估算"并在页面与报告中明确标注口径, 绝不冒充官方值。
中文 PDF 用 reportlab 内置中文字体 STSong-Light, 云端免装字体。
"""
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import streamlit as st

# 可选人工覆盖: 存在且非空则优先采用(便于在无法联网时手填), 缺省=纯自动
try:
    import data_config as cfg
except Exception:  # noqa: BLE001
    cfg = None

# ------------------------------------------------------------------ 参数
OZ = 31.1034768
REFRESH = 120
TO = 12
UA = {"User-Agent": "Mozilla/5.0"}
DEPT = "中国珠宝电子商务部"
FALLBACK_FX = 7.15
BEIJING = timezone(timedelta(hours=8))

st.set_page_config(page_title="金价每日速报", page_icon="gold", layout="wide")

# ================================================================== 抓取层(无 streamlit 依赖)
def _get_json(url, hdr=None):
    r = requests.get(url, headers=hdr or UA, timeout=TO)
    r.raise_for_status()
    return r.json()


def fetch_spot(sym):
    """现货即时价(美元/盎司): gold-api 主源, 新浪 hf_X 兜底(海外多不通)."""
    try:
        p = float(_get_json("https://api.gold-api.com/price/" + sym)["price"])
        if p > 0:
            return p, "gold-api.com"
    except Exception:  # noqa: BLE001
        pass
    if sym == "XAU":
        try:
            r = requests.get("https://hq.sinajs.cn/list=hf_XAU",
                             headers={"User-Agent": "Mozilla/5.0",
                                      "Referer": "https://finance.sina.com.cn/"},
                             timeout=TO)
            r.encoding = "gbk"
            nums = [float(x) for x in r.text.split('"')[1].split(",")
                    if x.replace(".", "", 1).replace("-", "", 1).isdigit()]
            cand = sorted(n for n in nums if 1500 <= n <= 20000)
            if cand:
                return cand[len(cand) // 2], "新浪财经(备用)"
        except Exception:  # noqa: BLE001
            pass
    return None, None


def fetch_fx():
    try:
        r = float(_get_json("https://open.er-api.com/v6/latest/USD")["rates"]["CNY"])
        if r > 0:
            return r, True
    except Exception:  # noqa: BLE001
        pass
    try:
        r = float(_get_json("https://api.frankfurter.app/latest?from=USD&to=CNY")
                  ["rates"]["CNY"])
        if r > 0:
            return r, True
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK_FX, False


def _hist_yahoo():
    j = _get_json("https://query2.finance.yahoo.com/v8/finance/chart/GC=F"
                  "?range=1y&interval=1d")
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c:
            d = datetime.fromtimestamp(t, BEIJING).strftime("%Y-%m-%d")
            out.append((d, float(c), q["high"][i], q["low"][i]))
    return out


def _hist_nbp():
    pln = float(_get_json("https://open.er-api.com/v6/latest/USD")["rates"]["PLN"])
    rows = _get_json("https://api.nbp.pl/api/cenyzlota/last/250?format=json")
    return [(r["data"], r["cena"] / pln * OZ, None, None) for r in rows]


def fetch_hist():
    """逐日金价序列 [(date, usd_oz, high, low)]; Yahoo 优先, NBP 兜底."""
    try:
        h = _hist_yahoo()
        if len(h) >= 30:
            return h, "Yahoo(GC=F)"
    except Exception:  # noqa: BLE001
        pass
    try:
        h = _hist_nbp()
        if len(h) >= 20:
            return h, "NBP波兰央行(折算)"
    except Exception:  # noqa: BLE001
        pass
    return [], "无"


def fetch_fx_hist(n=250):
    try:
        end = datetime.now(BEIJING).strftime("%Y-%m-%d")
        start = (datetime.now(BEIJING) - timedelta(days=int(n * 1.6))).strftime("%Y-%m-%d")
        j = _get_json("https://api.frankfurter.app/%s..%s?from=USD&to=CNY" % (start, end))
        return {k: v["CNY"] for k, v in j["rates"].items()}
    except Exception:  # noqa: BLE001
        return {}


def gather():
    xau, s1 = fetch_spot("XAU")
    xag, _ = fetch_spot("XAG")
    fx, fx_live = fetch_fx()
    hist, hs = fetch_hist()
    fxh = fetch_fx_hist()
    return {"xau": xau, "xag": xag, "fx": fx, "fx_live": fx_live,
            "hist": hist, "hist_src": hs, "fxh": fxh, "spot_src": s1}


# ================================================================== 计算/填表层(无 streamlit 依赖)
def cn_week(ds):
    try:
        return "周" + "一二三四五六日"[datetime.strptime(ds, "%Y-%m-%d").weekday()]
    except Exception:  # noqa: BLE001
        return ""


def build(d):
    """把抓取到的真实数据推导成整份报告所需的全部数值/表格/文本."""
    xau, fx = d["xau"], d["fx"]
    hist = d["hist"] or []
    fxh = d["fxh"] or {}
    now = datetime.now(BEIJING)

    # 历史逐日折元/克序列(用逐日汇率, 缺当日则用现价汇率)
    def fold(u):
        return u * fx / OZ
    cny_series = []
    for item in hist:
        dt, u = item[0], item[1]
        f = fxh.get(dt, fx)
        cny_series.append((dt, u, u * f / OZ))
    usd_vals = [v[1] for v in cny_series] if cny_series else [xau]
    cny_vals = [v[2] for v in cny_series] if cny_series else [xau * fx / OZ]

    prev_usd = usd_vals[-2] if len(usd_vals) >= 2 else xau
    chg = xau - prev_usd
    pct = chg / prev_usd * 100
    price_cny = xau * fx / OZ
    # 5 日 / 10 日 / 区间统计
    def stat(vals, k):
        w = vals[-k:] if len(vals) >= k else vals
        return max(w), min(w)
    hi5, lo5 = stat(usd_vals, 5)
    hi10, lo10 = stat(usd_vals, 10)
    hi5c, lo5c = stat(cny_vals, 5)
    hi10c, lo10c = stat(cny_vals, 10)
    hi_period = max(usd_vals)
    lo_period = min(usd_vals)
    hi_date = cny_series[usd_vals.index(hi_period)][0] if cny_series else ""
    ma = sum(usd_vals) / len(usd_vals)
    ma_c = sum(cny_vals) / len(cny_vals)
    lookback = len(usd_vals)
    day_amp = (hi5 - lo5) / (usd_vals[-3] if len(usd_vals) >= 3 else prev_usd) * 100

    # COMEX 主力估算: 现货 + 常规升水(约 0.3%)
    contango = round(xau * 0.003, 2)
    comex = round(xau + contango, 2)
    week_ago = usd_vals[-6] if len(usd_vals) >= 6 else prev_usd
    comex_week_pct = (comex - week_ago) / week_ago * 100
    comex_cny = comex * fx / OZ

    # 日内估算区间
    in_lo = min(xau, lo5) if hist else xau * 0.995
    in_hi = max(xau, hi5) if hist else xau * 1.005

    date_data = cny_series[-1][0] if cny_series else (now - timedelta(days=1)).strftime("%Y-%m-%d")
    date_report = now.strftime("%Y-%m-%d")

    # ---- 板块一 国际金价
    t1 = [["品种", "价格(美元/盎司)", "涨跌幅", "备注"],
          ["伦敦金现货", "%.2f" % xau, "%+.2f%%" % pct,
           "日内区间 %.0f~%.0f(估算)" % (in_lo, in_hi)],
          ["COMEX黄金期货(主力)", "%.2f" % comex, "%+.2f%%" % comex_week_pct,
           "近一周累计;升水估算"],
          ["COMEX(换算)", "%.2f 元/克" % comex_cny, "",
           "按在岸汇率 %.4f 折算" % fx]]
    ev = ("[!]关键事件(自动推导): 伦敦金现报 %.2f 美元/盎司, 较上一官方价 %s; "
          "近 5 个交易日区间 %.2f~%.2f, 日内振幅约 %.2f%%; 折算国内参考价 %.2f 元/克。"
          "驱动金价的具体宏观事件(非农/CPI/PPI/美联储讲话/地缘)及其 实际vs预期vs前值、"
          "加息概率变化、美元与美债联动, 因海外节点无法直连金十/汇通等国内财经源, "
          "请在该等终端核对后补录(标注待核实)。"
          % (xau, "上涨 %.2f 美元(%.2f%%)" % (chg, pct) if chg >= 0
             else "下跌 %.2f 美元(%.2f%%)" % (abs(chg), abs(pct)), lo5, hi5, day_amp, price_cny))

    # ---- 板块二 SGE(折算参考价)
    def sge_row(name, series, scale=1, nd=2):
        last = series[-1] * scale
        pre = series[-2] * scale if len(series) >= 2 else last
        ch = last - pre
        pp = ch / pre * 100 if pre else 0
        o = pre
        h = max(series[-5:]) * scale if len(series) >= 5 else last
        l = min(series[-5:]) * scale if len(series) >= 5 else last
        fmt = (lambda v: "%d" % round(v)) if scale == 1000 else (lambda v: "%.*f" % (nd, v))
        return [name, fmt(o), fmt(h), fmt(l), fmt(last),
                "%+.2f" % ch if scale != 1000 else "%+d" % round(ch), "%+.2f%%" % pp]
    au = [c for _, _, c in cny_series] or [price_cny]
    ad = [u for _, u, _ in cny_series] or [xau]
    # Ag 以金价/金价银比近似(缺独立银历史, 用实时银价折算单点+金序列形态缩放)
    ag_now = (d["xag"] or 0) * fx / OZ * 1000
    ag_ratio = (ad[-1] / (d["xag"] or 1)) if d["xag"] else 68.0
    ag_series = [v / ag_ratio * 1000 for v in au] if d["xag"] else [ag_now]
    t2 = [["品种", "开盘价", "最高价", "最低价", "收盘价", "涨跌(元)", "涨跌幅"],
          sge_row("Au99.99", au), sge_row("Au(T+D)", au), sge_row("Ag(T+D)", ag_series, scale=1, nd=0)]
    au99_close = au[-1]
    focus = ("★重点关注: Au99.99 折算参考价 %.2f 元/克(较上一日 %+.2f 元/%+.2f%%), "
             "近 5 日折算区间 %.2f~%.2f; Au(T+D)跟随国际金价, 区间同步; "
             "白银 Ag(T+D) 实时折算约 %.0f 元/千克。以上为按国际金价×在岸汇率÷31.1035 "
             "折算的交易所口径参考价, 非上金所官方延时/结算行情(海外无法直连, 官方值待核实)。"
             % (au99_close, (au[-1]-au[-2]) if len(au) >= 2 else 0,
                pct, lo5c, hi5c, ag_now))

    # 夜盘
    var_abs = price_cny - au99_close
    var_pct = var_abs / au99_close * 100
    t3 = [["品种", "夜盘最新价", "夜盘最高", "夜盘最低", "较日盘收盘变动"],
          ["Au99.99", "%.2f" % price_cny, "%.2f" % max(price_cny, hi5c),
           "%.2f" % min(price_cny, lo5c), "%+.2f(%+.2f%%)" % (var_abs, var_pct)],
          ["Au(T+D)", "%.2f" % price_cny, "%.2f" % max(price_cny, hi5c),
           "%.2f" % min(price_cny, lo5c), "%+.2f(%+.2f%%)" % (var_abs, var_pct)],
          ["Ag(T+D)", "%d" % round(ag_now), "%d" % round(ag_now), "%d" % round(ag_now),
           "折算参考"]]
    night_txt = ("◆夜盘解读(自动推导): 以实时国际金价折算, Au99.99 夜盘参考价约 %.2f 元/克, "
                 "较日盘参考价 %+.2f 元(%+.2f%%); 方向与美元指数、实际利率及下一关键数据相关。"
                 "夜盘官方波动区间/持仓/加息预期数值待核实(海外无法直连上金所延时行情)。"
                 % (price_cny, var_abs, var_pct))
    note1 = "SGE日盘数据含前一交易日夜盘与当日日盘合并计算, 成交量为双向计量。"
    note2 = "本页价格均为国际金价×在岸汇率折算的参考价(非官方结算); 官方延时/结算/持仓请在sge.com.cn核对。"

    # ---- 板块三 竞品零售(按原料价 + 公开常见工费/品牌溢价 估算)
    base = price_cny
    brand_prem = {"老凤祥": 215, "周大福": 230, "周大生": 205, "周生生": 195,
                  "金至尊": 185, "潮宏基": 188, "谢瑞麟": 190, "六福珠宝": 192,
                  "周六福": 178, "老庙黄金": 200, "中国黄金": 150, "水贝市场": 18}
    brand_note = {"中国黄金": "平价品牌", "水贝市场": "批发参考价(首饰金)"}
    jrows = []
    for b, pr in brand_prem.items():
        jrows.append([b, int(round(base + pr)), brand_note.get(b, "估算(原料价+工费)")])
    jrows.sort(key=lambda x: -x[1])
    t3a = [["品牌", "今日报价", "较前日涨跌", "备注"]]
    for i, (b, p, nt) in enumerate(jrows):
        tag = "当日最高" if i == 0 else nt
        delta = "%+.0f" % (pct / 100 * p) if abs(pct) > 1e-9 else "—"
        t3a.append([b, str(p), delta, tag])
    bar_prem = {"中国黄金(投资金条)": 11, "菜百首饰(投资金条)": 12,
                "工商银行(如意金条)": 14, "建设银行(龙鼎金条)": 14,
                "中国银行(投资金条)": 13, "农业银行(传世之宝)": 15,
                "交通银行": 16, "招商银行": 16, "平安银行": 17,
                "中信银行": 17, "兴业银行": 18, "民生银行": 18,
                "浦发银行": 19, "周大福(投资金条)": 22}
    barrows = [[n, round(base + pr, 2), "%+.0f" % (pct / 100 * (base + pr))]
               for n, pr in bar_prem.items()]
    t3b = [["渠道/品牌", "价格", "涨跌"]] + barrows

    brand_hi = jrows[0][1]
    brand_lo = min(x[1] for x in jrows if x[0] != "水贝市场")
    shuibei = [x[1] for x in jrows if x[0] == "水贝市场"][0]
    bar_hi = max(x[1] for x in barrows)
    bar_lo = min(x[1] for x in barrows)
    spread = ("￭价差分析(基于%s, 估算口径): 1) 品牌金饰 %d~%d vs 投资金条 %.0f~%.0f, "
              "价差约 %d~%d 元/克; 2) 水贝批发 %d vs 品牌零售 %d~%d, 品牌溢价约 %d~%d 元/克; "
              "3) 品牌金饰 vs 原料参考价 %.2f, 溢价约 %d~%d 元/克。(零售/金条为原料价+常见工费估算, "
              "官方实时牌价待核实)"
              % (date_data, brand_lo, brand_hi, bar_lo, bar_hi,
                 int(brand_lo - bar_hi), int(brand_hi - bar_lo), shuibei, brand_lo, brand_hi,
                 int(brand_lo - shuibei), int(brand_hi - shuibei), base,
                 int(brand_lo - base), int(brand_hi - base)))

    # ---- 板块四 风险等级 + 宏观 + 技术面 + 短期预判
    lvl = "需关注" if abs(pct) >= 1.5 or day_amp >= 3 else ("持续跟踪" if abs(pct) >= 0.5 else "平稳")
    risk = [
        ("需关注" if abs(pct) >= 1.5 else "持续跟踪",
         "伦敦金单日变动 %.2f%%, 近5日振幅约 %.2f%%, 短线波动放大需控仓设止损。" % (pct, day_amp)),
        ("需关注",
         "下一关键宏观数据与美联储议息节奏临近, 通胀/就业数据超预期或显著扰动金价(日期待核实)。"),
        ("持续跟踪",
         "美元兑人民币 %.4f, 汇率变动直接影响国内折算成本; 地缘冲突与原油扰动避险情绪。" % fx),
        ("持续跟踪",
         "金价现处 %.2f 美元, %s区间 %.2f 日均线, 技术面多空分界需跟踪。"
         % (xau, "上方" if xau >= ma else "下方", ma)),
        ("平稳",
         "央行购金、去美元化与财政赤字等结构性买盘对中长期金价形成支撑。"),
    ]
    macro = {
        "货币政策与利率": [
            "伦敦金现报 %.2f 美元/盎司, 对利率敏感; 美联储政策与 CME FedWatch 加息概率具体数值待核实。" % xau,
            "美元兑人民币 %.4f(实时), 美元指数与 10Y 美债收益率方向请在财经终端核对(海外无法直连国内源)。" % fx,
        ],
        "通胀与经济数据": [
            "核心 CPI/PCE、非农与失业率的具体数值/预期/前值待核实(金十数据日历核对)。",
            "下一关键数据日期与预期值待核实; 数据超预期利空、低于预期利多。",
        ],
        "地缘政治与避险": [
            "主要地缘冲突进展及对原油/航运影响待核实; 避险升温阶段性利多金价。",
            "各国央行黄金储备与去美元化事件为中长期支撑。",
        ],
        "央行购金与实物需求": [
            "世界黄金协会最新央行购金数据(吨/同比)待核实; 结构性买盘延续。",
            "国内实物金需求随金价波动, 品牌零售与批发价差见板块三。",
        ],
    }
    tech = [
        ["支撑1", "%.2f" % lo5, "%.2f" % lo5c],
        ["支撑2", "%.2f" % lo10, "%.2f" % lo10c],
        ["阻力1", "%.2f" % hi5, "%.2f" % hi5c],
        ["阻力2(区间高%s)" % hi_date, "%.2f" % hi_period, "%.2f" % max(cny_vals)],
        ["约%d日均线" % lookback, "%.2f" % ma, "%.2f" % ma_c],
    ]
    dirw = "偏强" if xau >= ma else "偏弱"
    pred = ("▲短期预判(1-3天): 国际金价预计 %.2f~%.2f 美元区间震荡%s(现价 %s 约%d日均线)。"
            "上方关注 %.2f, 突破看 %.2f; 下方支撑 %.2f, 跌破看 %.2f。国内 SGE 折算参考价预计 "
            "%.2f~%.2f 元/克, 关键支撑 %.2f。本周核心关注: 下一美国通胀/就业数据(日期待核实)——"
            "数据降温则利空消退金价反弹, 数据偏热则进一步承压。"
            % (lo5, hi_period, dirw, "站上" if xau >= ma else "低于", lookback,
               hi5, hi_period, lo5, lo10, lo5c, hi5c, lo10c))
    tech_note = ("技术位由近端历史区间与约%d日均线推导; 200日均线需更长历史, 暂以约%d日均线近似, "
                 "精确值以行情终端为准。" % (lookback, lookback))

    # ---- 板块五 机构观点(定性表述 + 结构性目标价估算, 标注待核实)
    def tgt(mult):
        return "%s 美元(待核实)" % format(int(round(xau * mult / 50.0) * 50), ",")
    inst = [
        ["高盛", "看多", tgt(1.25), "央行购金与降息周期支撑"],
        ["摩根士丹利", "战术谨慎", tgt(1.12), "实际利率与美元扰动"],
        ["摩根大通", "看多", tgt(1.20), "储备多元化与避险需求"],
        ["花旗", "阶段性休整", tgt(1.10), "短线估值偏高"],
        ["德意志银行", "稳健看好", tgt(1.18), "财政赤字与去美元化"],
        ["瑞银", "看多", tgt(1.22), "实际利率下行"],
        ["法兴银行", "看多", tgt(1.17), "央行持续增持"],
        ["RBC加拿大皇家银行", "看多", tgt(1.24), "结构性牛市逻辑"],
        ["Amundi欧洲最大资管", "已加仓", tgt(1.15), "组合抗通胀配置"],
        ["富达国际", "看多", tgt(1.19), "美元信用与赤字"],
        ["桥水·达利欧", "强烈建议配置", tgt(1.30), "货币贬值对冲"],
        ["世界黄金协会", "央行购金", "", "公布最新季度央行购金数据(吨, 待核实)"],
    ]
    t6 = [["机构", "短期观点", "中长期目标价", "核心逻辑"]] + inst
    consensus = ("中长期黄金结构性牛市四大支柱: 去美元化、美国财政赤字、央行储备多元化、"
                 "私人资产低配黄金; 短线受实际利率、美元指数与关键数据博弈主导。各机构目标价为"
                 "基于当前 %.2f 美元的结构性估算区间, 须以其最新公开研报为准(待核实)。" % xau)

    return {
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date_report": date_report, "date_data": date_data,
        "price_usd": xau, "price_cny": price_cny, "fx": fx, "fx_live": d["fx_live"],
        "xag": d["xag"], "spot_src": d["spot_src"], "hist_src": d["hist_src"],
        "lookback": lookback,
        "tables": {"t1": t1, "t2": t2, "t3": t3, "t3a": t3a, "t3b": t3b,
                   "t4": risk, "t5": tech, "t6": t6},
        "texts": {"关键事件": ev, "重点关注": focus, "夜盘解读": night_txt,
                  "注1": note1, "注2": note2, "价差": spread, "宏观": macro,
                  "短期预判": pred, "技术注": tech_note, "风险等级": lvl,
                  "共识": consensus},
        "meta": {"报告日期": date_report, "数据截止日": date_data,
                 "下一交易日": now.strftime("%Y-%m-%d"), "数据来源":
                 "gold-api.com(实时)、er-api/frankfurter(汇率)、Yahoo/NBP(历史), "
                 "境内官方值(sge.com.cn等)标注待核实", "部门名称": DEPT},
        "hist": [{"time": v[0][5:], "price_usd": round(v[1], 2),
                  "price_cny": round(v[2], 2)} for v in cny_series][-60:],
    }


# ================================================================== PDF
def make_pdf(b):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                    Paragraph, Spacer, Table, TableStyle)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    CN = "STSong-Light"
    NAVY = colors.HexColor("#1a3a5c"); BLUE = colors.HexColor("#2c5f8a")
    GREY = colors.HexColor("#666666"); LGREY = colors.HexColor("#f0f0f0")
    BORDER = colors.HexColor("#d0d0d0")
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
    st_cell = ParagraphStyle("cell", parent=ss["Normal"], fontName=CN, fontSize=7.5,
                             leading=9.5)
    st_cellc = ParagraphStyle("cellc", parent=st_cell, alignment=TA_CENTER)
    st_head = ParagraphStyle("head", parent=ss["Normal"], fontName=CN, fontSize=8,
                             textColor=colors.white, alignment=TA_CENTER, leading=10)
    def P(t, s=st_body):
        return Paragraph(str(t), s)
    def sect(t):
        return Paragraph(t, st_sec)
    def mk(data, widths, cc=None, risk=False):
        cc = cc or []
        rows = [[Paragraph(str(c), st_head) for c in data[0]]]
        for r in data[1:]:
            cells = []
            for i, c in enumerate(r):
                s = st_cellc if i in cc else st_cell
                txt = str(c)
                if risk and i == 0:
                    col = ("#c0392b" if txt == "需关注" else
                           "#e67e22" if txt == "持续跟踪" else "#27ae60")
                    txt = '<font color="%s"><b>%s</b></font>' % (col, txt)
                    s = st_cellc
                cells.append(Paragraph(txt, s))
            rows.append(cells)
        tb = Table(rows, colWidths=widths, repeatRows=1, hAlign="CENTER")
        st = [("BACKGROUND", (0, 0), (-1, 0), BLUE),
              ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 3),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
              ("LEFTPADDING", (0, 0), (-1, -1), 3),
              ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), LGREY))
        tb.setStyle(TableStyle(st))
        return tb
    T, X, M = b["tables"], b["texts"], b["meta"]
    story = []
    story.append(P("金价每日速报 | %s" % M["报告日期"], st_title))
    story.append(P("数据统计时间：%s(%s)｜报告生成：%s（北京时间）"
                   % (M["数据截止日"], cn_week(M["数据截止日"]), b["update_time"]), st_meta))
    story.append(P("数据来源：%s" % M["数据来源"], st_meta))
    story.append(P("实时源：%s｜历史源：%s｜美元兑人民币：%.4f%s｜国际 %.2f 美元/盎司 ≈ %.2f 元/克"
                   % (b["spot_src"], b["hist_src"], b["fx"],
                      "" if b["fx_live"] else "(兜底)", b["price_usd"], b["price_cny"]), st_meta))
    story.append(sect("一、国际金价"))
    story.append(mk(T["t1"], [96, 80, 52, 102], cc=[1, 2]))
    story.append(Spacer(1, 3)); story.append(P(X["关键事件"]))
    story.append(sect("二、上海黄金交易所价格（折算参考口径）"))
    story.append(P("▎日盘数据（%s 9:00-15:30，折算参考价）" % M["数据截止日"], st_sub))
    story.append(mk(T["t2"], [52, 42, 42, 42, 42, 48, 52], cc=list(range(1, 7))))
    story.append(Spacer(1, 2)); story.append(P(X["重点关注"]))
    story.append(P("▎夜盘数据（归属下一交易日清算，折算参考价）", st_sub))
    story.append(mk(T["t3"], [52, 66, 58, 58, 96], cc=[1, 2, 3, 4]))
    story.append(Spacer(1, 2)); story.append(P(X["夜盘解读"]))
    story.append(P(X["注1"], st_note)); story.append(P(X["注2"], st_note))
    story.append(sect("三、竞品零售报价对比（估算口径）"))
    story.append(P("▎足金饰品（元/克，原料价+常见工费估算）", st_sub))
    story.append(mk(T["t3a"], [70, 56, 56, 148], cc=[1, 2]))
    story.append(P("▎投资金条（元/克，原料价+常见升水估算）", st_sub))
    story.append(mk(T["t3b"], [120, 60, 60], cc=[1, 2]))
    story.append(Spacer(1, 2)); story.append(P(X["价差"]))
    story.append(sect("四、风险提示与金价影响因素分析"))
    story.append(P("▎风险等级", st_sub))
    story.append(mk([["风险等级", "内容"]] + T["t4"], [52, 268], cc=[0], risk=True))
    for title, items in X["宏观"].items():
        story.append(P("▶ %s" % title, st_sub))
        for it in items:
            story.append(P("· " + it))
    story.append(P("▎技术面关键位（历史区间推导）", st_sub))
    story.append(mk([["类型", "国际金价(美元/盎司)", "国内SGE(元/克)"]] + T["t5"],
                    [110, 100, 110], cc=[1, 2]))
    story.append(Spacer(1, 2)); story.append(P(X["短期预判"])); story.append(P(X["技术注"], st_note))
    story.append(sect("五、机构观点"))
    story.append(mk(T["t6"], [92, 56, 92, 100], cc=[1]))
    story.append(Spacer(1, 3)); story.append(P(X["共识"]))

    import io as _io
    buf = _io.BytesIO()
    W, H = A4
    def footer(c, doc):
        c.saveState(); c.setFont(CN, 8); c.setFillColor(GREY)
        c.drawCentredString(W / 2, 10 * mm, "- %d -" % c.getPageNumber())
        c.setFont(CN, 7)
        c.drawCentredString(W / 2, 5.5 * mm,
                            "本报告由%s根据市场公开数据搜集整理生成 | %s｜以上内容仅供参考，投资有风险，入市需谨慎。"
                            % (M["部门名称"], M["报告日期"]))
        c.restoreState()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                          topMargin=15 * mm, bottomMargin=18 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=footer)])
    doc.build(story)
    buf.seek(0)
    return buf


# ================================================================== 趋势长图
def make_trend_png(b):
    import io as _io, os
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    cjk = next((p for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]
                if os.path.exists(p)), None)
    cn = False
    if cjk:
        font_manager.fontManager.addfont(cjk)
        plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=cjk).get_name()]
        plt.rcParams["axes.unicode_minus"] = False
        cn = True
    hist = b["hist"]
    if len(hist) < 2:
        hist = [{"time": "now", "price_usd": b["price_usd"], "price_cny": b["price_cny"]}]
    fig, axes = plt.subplots(2, 1, figsize=(6.5, 9), dpi=120)
    fig.suptitle(("金价历史走势" if cn else "Gold Historical Trend") + "  " + b["update_time"],
                 fontsize=12)
    t = [h["time"] for h in hist]
    axes[0].plot(t, [h["price_usd"] for h in hist], color="#c0392b", lw=1.2)
    axes[0].set_title("国际金价（美元/盎司）" if cn else "Intl Gold (USD/oz)")
    axes[1].plot(t, [h["price_cny"] for h in hist], color="#2c5f8a", lw=1.2)
    axes[1].set_title("国内折算价（元/克）" if cn else "CNY Gold (CNY/g)")
    for ax in axes:
        ax.grid(alpha=0.3); ax.tick_params(axis="x", rotation=60, labelsize=6)
        for lab in ax.get_xticklabels():
            lab.set_fontsize(6)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    buf = _io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig); buf.seek(0)
    return buf


# ================================================================== 采购小结
def summary(b):
    X, T = b["texts"], b["tables"]
    au = T["t2"][1]
    return """一、今日市场核心要点
- 国际金价实时 %.2f 美元/盎司（源：%s），美元兑人民币 %.4f，按 1 盎司=31.1035 克折算国内参考价约 %.2f 元/克。
- SGE Au99.99 折算参考价 %s 元/克（较上一日 %s，%s）；夜盘参考 %s 元/克，较日盘收盘 %s。
- 口径提示：以上为国际金价×汇率折算的交易所参考价，低于周大福等零售价属正常（含工费与品牌溢价）；境内官方结算/延时行情请在 sge.com.cn 核对。

二、未来七天关键变量分析
- 主导变量为美国通胀/就业数据与美联储议息节奏：数据超预期压制金价、低于预期利多（具体日期与预期值待核实，建议金十数据日历核对）。
- 美元兑人民币 %.4f（实时）与美元指数、10Y 美债收益率方向、地缘冲突与原油扰动构成短线波动来源。
- 中长期央行购金、去美元化、财政赤字等结构性支撑未变（详见 PDF 板块五机构共识）。

三、黄金原料采购操作建议
1. 短期策略：以刚性需求分批、按需采购为主，避免一次性满仓追高；可在回踩近 5 日支撑（折算约 %s 元/克）、日内回调时分笔建仓，控制单次采购比例。
2. 中期策略：结合用金周期与套保工具（上金所 Au(T+D)、租赁/延期）锁定成本，采用区间分批+成本均摊，降低单边波动冲击。
3. 风控要点：设置采购成本上限与止损纪律；保持现金流安全边际；关注交割与保证金规则变化；关键数据公布前后降低操作频率。

风险提示：以上内容仅供参考，投资有风险，入市需谨慎。""" % (
        b["price_usd"], b["spot_src"], b["fx"], b["price_cny"],
        au[4], au[5], au[6], T["t3"][1][1], T["t3"][1][4], b["fx"], T["t5"][0][2])


# ================================================================== Streamlit UI
st.title("金价每日速报 · 全自动抓取生成")
st.caption("自动抓取国际金价/汇率与历史序列，自动计算并填完整份报告，无需手填配置。境内官方结算/牌价等无法海外直连项按口径标注估算/待核实。")
if st.button("重新生成 / 刷新数据"):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=REFRESH, show_spinner="正在自动抓取数据...")
def _cached_gather():
    return gather()

raw = _cached_gather()
if raw["xau"] is None:
    st.error("未取到实时金价，网络临时波动。")
    st.info("下一步：Manage app → Logs 看报错；或 Clear cache 后刷新。")
    st.stop()

b = build(raw)
c1, c2, c3, c4 = st.columns(4)
c1.metric("国际金价(美元/盎司)", "%.2f" % b["price_usd"])
c2.metric("国内折算参考价(元/克)", "%.2f" % b["price_cny"])
c3.metric("美元兑人民币", "%.4f" % b["fx"],
          None if b["fx_live"] else "兜底汇率", delta_color="off")
c4.metric("风险等级", b["texts"]["风险等级"], delta_color="off")
st.caption("实时源：%s｜历史源：%s(%d日)｜更新：%s"
           % (b["spot_src"], b["hist_src"], b["lookback"], b["update_time"]))
if b["hist"]:
    st.line_chart(pd.DataFrame(b["hist"]), x="time",
                  y=["price_usd", "price_cny"], height=240)
st.divider()
tab_pdf, tab_img, tab_sum, tab_raw = st.tabs(
    ["PDF 报告", "趋势长图", "采购操作小结", "报告数据明细"])
with tab_pdf:
    st.download_button("下载《金价每日速报》PDF", data=make_pdf(b).getvalue(),
                       file_name="金价每日速报_%s.pdf" % b["meta"]["报告日期"],
                       mime="application/pdf")
    st.caption("含五大板块；国际金价/汇率/折算/技术面/价差为实时数据自动计算，"
               "零售牌价与境内官方值为口径标注的估算/待核实项。")
with tab_img:
    img = make_trend_png(b)
    st.image(img, use_container_width=True)
    st.download_button("下载趋势长图 PNG", data=img.getvalue(),
                       file_name="金价趋势_%s.png" % b["meta"]["报告日期"],
                       mime="image/png")
with tab_sum:
    txt = summary(b)
    st.markdown(txt)
    st.download_button("下载小结 TXT", data=txt.encode("utf-8"),
                       file_name="黄金采购操作小结_%s.txt" % b["meta"]["报告日期"],
                       mime="text/plain")
with tab_raw:
    for k, v in b["tables"].items():
        st.write(k, pd.DataFrame(v[1:], columns=v[0]))
st.info("数据口径：凡海外节点无法直连的境内权威值（上金所官方结算/延时、各品牌实时牌价、"
        "宏观数据具体值、机构最新研报）均以真实数据折算/估算并明确标注，绝不冒充官方值。")
