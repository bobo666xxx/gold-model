#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金价每日速报生成器 —— Streamlit 网页版入口（streamlit_app.py）

配套文件（三个文件必须放在 GitHub 仓库根目录，缺一不可）
    streamlit_app.py       本文件，Streamlit 网页入口（部署时选它作为 App entry point）
    gold_price_report.py   核心模块，Prompt / Markdown / PDF 的全部逻辑都在这里
    requirements.txt       依赖清单（streamlit / pandas / reportlab）

为什么之前"不能运行"
    gold_price_report.py 本身是一个命令行脚本（argparse），它不会画界面。
    Streamlit 需要一个持续运行并调用 st.* 绘制界面的入口文件，
    直接把命令行脚本当入口部署，页面就是空白或报 "could not find source file"。
    本文件就是那个入口：requirements.txt 负责装依赖，本文件负责跑界面。

本地自测
    pip install -r requirements.txt
    streamlit run streamlit_app.py

线上部署（Streamlit 社区云，免费）
    1. 三个文件推到 GitHub 仓库根目录（建议 main 分支）。
    2. 打开 share.streamlit.io/deploy，登录 GitHub，New app，
       依次选 Repository / Branch / Main file path = streamlit_app.py，Deploy。
    3. 构建日志出现 "Installing requirements" 说明 requirements.txt 被正确读取。
    4. 免费实例闲置后会休眠，重新访问冷启动约 10~30 秒，属正常现象，不是报错。

中文字体说明
    社区云的容器里通常没有中文字体，导出的 PDF 中文会变方块。
    解决办法：在仓库根目录新建 fonts 目录，放进一个中文 ttf/ttc 字体
    （如 simhei.ttf / NotoSansCJK-Regular.ttc），本文件会自动搜索并加载；
    也可以直接在侧边栏"PDF 中文字体"处临时上传一个字体文件。
"""

from __future__ import annotations

import datetime as _dt
import glob
import importlib.util
import json
import os
import sys
import tempfile

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# 一、导入核心模块（找不到时给出可执行的修复提示，而不是抛裸异常）
# ---------------------------------------------------------------------------
try:
    import gold_price_report as gpr
    MODULE_OK = True
    MODULE_ERR = ''
except Exception as exc:  # pragma: no cover
    gpr = None
    MODULE_OK = False
    MODULE_ERR = repr(exc)

HAS_PDF = importlib.util.find_spec('reportlab') is not None

# ---------------------------------------------------------------------------
# 二、界面基础设置
# ---------------------------------------------------------------------------
st.set_page_config(page_title='金价每日速报生成器', layout='wide', initial_sidebar_state='expanded')

FONT_KEYWORDS = ('cjk', 'hei', 'song', 'kai', 'noto', 'wqy', 'uming', 'ukai',
                 'arphic', 'droidsansfallback', 'sourcehansans', 'pingfang', 'simhei', 'simfang')


def find_cjk_font() -> str:
    """搜索可用中文字体：仓库 fonts 目录 -> 系统字体目录 -> 临时字体目录。"""
    roots = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts'),
        os.path.join(tempfile.gettempdir(), 'gpr_fonts'),
        '/usr/share/fonts',
        '/System/Library/Fonts',
        'C:/Windows/Fonts',
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for path in glob.glob(os.path.join(root, '**', '*.*'), recursive=True):
            low = os.path.basename(path).lower()
            if not low.endswith(('.ttf', '.ttc', '.otf')):
                continue
            if any(k in low for k in FONT_KEYWORDS):
                return path
    return ''


def patch_module_font(font_path: str) -> None:
    """让核心模块优先使用搜索到的中文字体（不修改其源码）。"""
    if not (MODULE_OK and font_path):
        return
    original = getattr(gpr, '_find_cjk_font', None)

    def patched(_name: str = ''):
        return font_path

    if original is not None:
        gpr._find_cjk_font = patched  # type: ignore[attr-defined]


def demo_payload():
    cfg = gpr.ReportConfig(report_date='2026-09-07', data_date='2026-09-05',
                           output_date='2026-09-08', gen_time='09:00', fx_rate=6.72,
                           key_data='9月10日PPI、9月11日CPI', fomc_date='9月15-16日')
    data = gpr.ReportData(
        intl=[{'name': '伦敦金现货', 'note': '待核实'},
              {'name': 'COMEX黄金期货(12月合约)', 'note': '待核实'},
              {'name': 'COMEX黄金(换算)'}],
        sge_day=[{'name': p, 'note': ''} for p in gpr.SGE_PRODUCTS],
        sge_night=[{'name': p, 'note': ''} for p in gpr.SGE_PRODUCTS],
        brands=[{'brand': b, 'note': ''} for b in gpr.BRAND_LIST],
        bullion=[{'name': n} for n in gpr.BULLION_LIST],
        risk=[{'level': lv, 'content': '待填（事件+影响程度+时间节点）'} for lv in gpr.RISK_LEVELS],
        tech=[{'type': t} for t in gpr.TECH_LEVELS],
        institutions=[{'org': o} for o in gpr.INSTITUTION_LIST])
    return cfg, data


# ---------------------------------------------------------------------------
# 三、侧边栏：报告参数（对应模板第九节「可调整变量速查表」）
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title('金价每日速报生成器')
    st.caption('把《金价每日速报_AI指令模板008》变成可填、可算、可导出的在线工具')

    today = _dt.date.today()
    report_date = st.date_input('报告日期 report_date', today)
    data_date = st.date_input('数据统计截止日 data_date（上一交易日）',
                              today - _dt.timedelta(days=2))
    output_date = st.date_input('夜盘归属交易日 output_date', today + _dt.timedelta(days=1))
    gen_time = st.text_input('报告生成时间 gen_time', _dt.datetime.now().strftime('%H:%M'))
    dept = st.text_input('出具部门 dept', '中国珠宝电子商务部')
    fx_rate = st.number_input('在岸人民币收盘汇率 fx_rate', 1.0, 20.0, 6.72, 0.0001, format='%.4f')
    key_data = st.text_input('下周关键数据日期 key_data', '待核实')
    fomc_date = st.text_input('下次 FOMC 会议日期 fomc_date', '待核实')
    extra_notes = st.text_area('附加说明 extra_notes（追加到指令末尾，可留空）', '')

    st.divider()
    font_path = find_cjk_font()
    upl = st.file_uploader('PDF 中文字体（社区云无中文字体时上传，选填）',
                           type=['ttf', 'ttc', 'otf'])
    if upl is not None:
        font_dir = os.path.join(tempfile.gettempdir(), 'gpr_fonts')
        os.makedirs(font_dir, exist_ok=True)
        font_path = os.path.join(font_dir, upl.name)
        with open(font_path, 'wb') as fp:
            fp.write(upl.getbuffer())
    if not MODULE_OK:
        st.error('未找到 gold_price_report.py。请把核心模块与本文件、requirements.txt '
                 '一起放到仓库根目录。')
        st.stop()
    patch_module_font(font_path)

    with st.expander('部署与环境自检'):
        st.write(f'核心模块版本：{gpr.__version__}')
        st.write(f'Python：{sys.version.split()[0]}')
        st.write(f'streamlit：{st.__version__}')
        st.write(f'reportlab（PDF 导出）：{"已安装" if HAS_PDF else "未安装，请检查 requirements.txt"}')
        st.write(f'中文字体：{font_path if font_path else "未找到，PDF 中文可能显示为方块"}')
        st.write(f'云环境：{st.runtime.exists()}')
        st.markdown('仓库根目录需要三个文件：`streamlit_app.py`、`gold_price_report.py`、'
                    '`requirements.txt`。部署时 Main file path 选 `streamlit_app.py`。')

# ---------------------------------------------------------------------------
# 四、主界面
# ---------------------------------------------------------------------------
cfg = gpr.ReportConfig(report_date=str(report_date), data_date=str(data_date),
                       output_date=str(output_date), gen_time=gen_time, dept=dept,
                       fx_rate=float(fx_rate), key_data=key_data, fomc_date=fomc_date,
                       extra_notes=extra_notes)

st.subheader(f'报告参数确认　{cfg.report_date}　数据统计 {cfg.data_date}　夜盘归属 {cfg.output_date}')
st.dataframe(pd.DataFrame(gpr.VARIABLE_TABLE, columns=['变量', '取值口径', '示例值']),
             use_container_width=True, hide_index=True)

tab_pd, tab_intl, tab_sge, tab_retail, tab_risk, tab_out, tab_tool = st.tabs(
    ['报告说明', '板块一 国际金价', '板块二 上金所', '板块三 零售报价',
     '板块四 风险与观点', '导出产物', '计算与质检'])

# ---- 报告说明 ----
with tab_pd:
    st.markdown('左侧填参数，各板块页签录入已核实的数据，最后在**导出产物**页取三样东西：'
                '下达给 AI 的完整指令文本、报告 Markdown 骨架、A4 PDF。')
    st.markdown('**数据来源优先级（模板第二节，必须交叉验证）**')
    for order, src in gpr.DATA_SOURCES:
        st.markdown(f'{order}. {src}')
    st.markdown('**交叉验证规则**')
    for rule in gpr.CROSS_VALIDATION_RULES:
        st.markdown(f'- {rule}')
    st.info('模板要求：所有数据必须来自公开可查渠道，禁止编造；未填字段一律按"待核实"处理，'
            '本工具不会自动补任何行情数字。')

# ---- 数据录入表格 ----
def edit_table(rows, columns, widget_key):
    df = pd.DataFrame(rows, columns=list(columns.keys()))
    return st.data_editor(df, column_config={k: st.column_config.Column(v) for k, v in columns.items()},
                          key=widget_key, use_container_width=True,
                          num_rows='dynamic', hide_index=True)


def clean(df: pd.DataFrame, keys) -> list:
    out = []
    for rec in df.to_dict('records'):
        rec = {k: (None if (v is None or (isinstance(v, float) and pd.isna(v)) or v == '') else v)
               for k, v in rec.items() if k in keys}
        if any(v not in (None, '') for v in rec.values()):
            out.append(rec)
    return out


with tab_intl:
    st.caption('表格 4 列：品种 / 价格(美元/盎司) / 涨跌幅 / 备注（备注 15 字以内，禁止溢出表格）')
    df1 = edit_table([{'name': '伦敦金现货', 'price': None, 'chg': None, 'note': '待核实'},
                                    {'name': 'COMEX黄金期货(12月合约)', 'price': None, 'chg': None, 'note': '待核实'},
                                    {'name': 'COMEX黄金(换算)', 'price': None, 'chg': None, 'note': f'按汇率 {fx_rate} 换算元/克'}],
                     {'name': '品种', 'price': '价格(美元/盎司)', 'chg': '涨跌幅', 'note': '备注'},
                     'intl_table')
    key_events = st.text_area('[!]关键事件（核心宏观事件 + 实际值/预期值/前值 + 金价即时反应 + 政策预期与美元美债联动）', '')
    st.caption(f'按在岸汇率 {fx_rate} 换算：COMEX 价格 × 汇率 ÷ 31.1035 = 元/克（可在计算页签反算校验）')

with tab_sge:
    st.markdown(f'**日盘数据（{cfg.prev_trade_date} 9:00-15:30）** 涨跌幅由收盘价与前收盘价自动算出')
    df2 = st.data_editor(
        pd.DataFrame([{'name': p, 'open': None, 'high': None, 'low': None,
                       'close': None, 'prev_close': None} for p in gpr.SGE_PRODUCTS]),
        column_config={
            'name': st.column_config.TextColumn('品种'),
            'open': st.column_config.NumberColumn('开盘价', format='%.2f'),
            'high': st.column_config.NumberColumn('最高价', format='%.2f'),
            'low': st.column_config.NumberColumn('最低价', format='%.2f'),
            'close': st.column_config.NumberColumn('收盘价', format='%.2f'),
            'prev_close': st.column_config.NumberColumn('前收盘价', format='%.2f')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='sge_day')
    focus_note = st.text_area('★重点关注（收盘价与盘中高低、振幅、Au(T+D) 放量缩量、白银表现）', '')

    st.markdown(f'**夜盘数据（{cfg.prev_trade_date} 20:00 — {cfg.data_date} 02:30，'
                f'属 {cfg.output_date} 交易日）** 较日盘变动 = 最新价 − 日盘收盘（元 与 % 同时显示）')
    df3 = st.data_editor(
        pd.DataFrame([{'name': p, 'last': None, 'high': None, 'low': None,
                       'day_close': None} for p in gpr.SGE_PRODUCTS]),
        column_config={
            'name': st.column_config.TextColumn('品种'),
            'last': st.column_config.NumberColumn('夜盘最新价', format='%.2f'),
            'high': st.column_config.NumberColumn('夜盘最高', format='%.2f'),
            'low': st.column_config.NumberColumn('夜盘最低', format='%.2f'),
            'day_close': st.column_config.NumberColumn('日盘收盘价', format='%.2f')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='sge_night')
    night_note = st.text_area('◆夜盘解读（驱动因素、波动区间与关键点位、美元指数与加息预期、下一关键数据）', '')
    st.caption('注1：SGE 日盘数据含前一交易日夜盘与当日日盘合并计算，成交量为双向计量。'
               '注2：夜盘数据需上金所延时行情与汇通财经、金投网交叉验证，涨跌幅以日盘收盘为基准。')

with tab_retail:
    st.markdown(f'**足金饰品（元/克，{cfg.data_date} 白天报价，按价格从高到低排列）**')
    df4 = st.data_editor(
        pd.DataFrame([{'brand': b, 'price': None, 'chg': None, 'note': ''} for b in gpr.BRAND_LIST]),
        column_config={
            'brand': st.column_config.TextColumn('品牌'),
            'price': st.column_config.NumberColumn('今日报价(元/克)', format='%.0f'),
            'chg': st.column_config.NumberColumn('较前日涨跌', format='%.0f'),
            'note': st.column_config.TextColumn('备注')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='brands')
    st.markdown(f'**投资金条（元/克，{cfg.data_date}）** 无数据留空，导出时自动填为长横杠')
    df5 = st.data_editor(
        pd.DataFrame([{'name': n, 'price': None, 'chg': None} for n in gpr.BULLION_LIST]),
        column_config={
            'name': st.column_config.TextColumn('渠道/品牌'),
            'price': st.column_config.NumberColumn('价格', format='%.2f'),
            'chg': st.column_config.NumberColumn('涨跌', format='%.2f')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='bullion')
    spread_note = st.text_area('￭价差分析（品牌金饰 vs 投资金条 / 水贝批发 vs 品牌零售 / 品牌金饰 vs Au99.99 原料价）', '')

with tab_risk:
    st.markdown('**风险等级（需关注 红色加粗 / 持续跟踪 橙色加粗 / 平稳 绿色加粗）**')
    df6 = st.data_editor(
        pd.DataFrame([{'level': lv, 'content': ''} for lv in gpr.RISK_LEVELS]),
        column_config={'level': st.column_config.SelectboxColumn('风险等级', options=gpr.RISK_LEVELS),
                       'content': st.column_config.TextColumn('内容（事件+影响程度+关键时间节点）')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='risk')
    st.markdown('**技术面关键位**')
    df7 = st.data_editor(
        pd.DataFrame([{'type': t, 'pos': None, 'intl': None, 'sge': None} for t in gpr.TECH_LEVELS]),
        column_config={'type': st.column_config.TextColumn('类型'),
                       'pos': st.column_config.NumberColumn('点位方向', format='%.2f'),
                       'intl': st.column_config.NumberColumn('国际金价位', format='%.2f'),
                       'sge': st.column_config.NumberColumn('上金所价位', format='%.2f')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='tech')
    short_term = st.text_area('▲短期预判', '')
    st.markdown('**机构观点（模板要求至少 10 家）**')
    df8 = st.data_editor(
        pd.DataFrame([{'org': o, 'view': '', 'target': '', 'logic': ''} for o in gpr.INSTITUTION_LIST]),
        column_config={'org': st.column_config.TextColumn('机构'),
                       'view': st.column_config.TextColumn('观点'),
                       'target': st.column_config.TextColumn('目标价'),
                       'logic': st.column_config.TextColumn('核心逻辑')},
        use_container_width=True, num_rows='dynamic', hide_index=True, key='institutions')
    consensus = st.text_area('机构共识小结', '')

data = gpr.ReportData(
    intl=clean(df1, ('name', 'price', 'chg', 'note')),
    sge_day=clean(df2, ('name', 'open', 'high', 'low', 'close', 'prev_close')),
    sge_night=clean(df3, ('name', 'last', 'high', 'low', 'day_close')),
    brands=clean(df4, ('brand', 'price', 'chg', 'note')),
    bullion=clean(df5, ('name', 'price', 'chg')),
    risk=clean(df6, ('level', 'content')),
    tech=clean(df7, ('type', 'pos', 'intl', 'sge')),
    institutions=clean(df8, ('org', 'view', 'target', 'logic')),
    key_events=key_events, focus_note=focus_note, night_note=night_note,
    spread_note=spread_note, short_term=short_term, consensus=consensus)

# ---- 导出 ----
prompt_text = gpr.build_prompt(cfg, data)
md_text = gpr.build_markdown(cfg, data)

with tab_out:
    st.download_button('下载 AI 指令文本 Prompt（.txt）', prompt_text.encode('utf-8'),
                       file_name=f'金价每日速报_指令_{cfg.report_date}.txt', mime='text/plain')
    st.download_button('下载报告 Markdown 骨架（.md）', md_text.encode('utf-8'),
                       file_name=f'金价每日速报_{cfg.report_date}.md', mime='text/markdown')
    st.download_button('下载参数配置（.json）',
                       json.dumps(dict(cfg.__dict__), ensure_ascii=False, indent=2,
                                  default=str).encode('utf-8'),
                       file_name=f'config_{cfg.report_date}.json', mime='application/json')

    if HAS_PDF:
        if st.button('生成 A4 PDF', type='primary'):
            pdf_path = os.path.join(tempfile.gettempdir(), f'金价每日速报_{cfg.report_date}.pdf')
            try:
                with st.spinner('正在按模板第六节排版规范渲染 A4 PDF...'):
                    gpr.render_pdf(cfg, data, pdf_path)
                with open(pdf_path, 'rb') as fp:
                    st.download_button('下载 A4 PDF', fp.read(),
                                       file_name=f'金价每日速报_{cfg.report_date}.pdf',
                                       mime='application/pdf', type='primary')
                if not font_path:
                    st.warning('未检测到中文字体，PDF 里的中文可能显示为方块。'
                               '请在仓库根目录 fonts 目录放一个中文 ttf/ttc 字体，或在左侧临时上传。')
            except Exception as exc:
                st.error(f'PDF 渲染失败：{exc}')
    else:
        st.error('未安装 reportlab，无法导出 PDF。请确认 requirements.txt 已随仓库上传，'
                 '并在 Streamlit 的 Requirements 标签页查看依赖安装日志。')

    st.markdown('**下达给 AI 的完整指令预览**')
    st.text_area('Prompt（可直接复制给 AI，或下载为 txt）', prompt_text, height=420)

with tab_tool:
    st.markdown('### 计算工具（模板第七节规则，独立可算）')
    c1, c2, c3 = st.columns(3)
    with c1:
        close = st.number_input('收盘价', 0.0, None, 776.4, 0.01)
        prev_close = st.number_input('前收盘价', 0.0, None, 773.1, 0.01)
        st.write('涨跌幅：', gpr.pct_change(close, prev_close))
        st.write('振幅：', gpr.amplitude(close + 2, close - 4, prev_close))
    with c2:
        oz = st.number_input('COMEX 价格（美元/盎司）', 0.0, None, 3612.50, 0.01)
        st.write('换算元/克：', gpr.comex_to_cny_per_gram(oz, float(fx_rate)))
        nl = st.number_input('夜盘最新价', 0.0, None, 770.0, 0.01)
        st.write('较日盘变动：', gpr.night_change(nl, close))
    with c3:
        vol = st.number_input('成交量/持仓（整数）', 0, None, 123456, 1)
        st.write('千分位：', gpr.thousand_sep(vol))
        st.write('带正负号：', gpr.signed(3.2))
        st.write('星期：', gpr.weekday_cn(str(data_date)))

    st.markdown('### 质检清单（模板第八节）')
    results = gpr.quality_check(cfg, data)
    for ok, item in results:
        st.markdown(('通过　' if ok else '待办　') + item)

st.caption('数据来源：上海黄金交易所官网延时行情、金融界、新浪财经、每经AI、金投网、金价查询网、'
           '21世纪经济报道、汇通财经、金十数据等 | 以上内容仅供参考，投资有风险，入市需谨慎')
