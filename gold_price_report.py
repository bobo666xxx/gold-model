#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金价每日速报生成器 (Gold Price Daily Report Builder)

本脚本由《金价每日速报_AI指令模板008.docx》逐条转录而来，把原本写给 AI 的自然语言
Prompt 模板改造成可版本化、可复用、可参数化的 Python 模块，适合放入 GitHub 仓库
（例如 gold-model）直接作为 app.py 使用。

功能一览
    1. 完整内置模板规范：角色定位 / 数据来源优先级 / 交叉验证规则 / 五大板块指令 /
       报告头部与页脚 / PDF 排版规范 / 计算规则 / 质检清单 / 变量速查表
    2. 参数化配置 ReportConfig：报告日期、数据截止日、下一交易日、生成时间、部门名称、
       在岸汇率、关键数据日期、FOMC 会议日期
    3. 一键构建下达给 AI 的完整 Prompt 文本：build_prompt()
    4. 内置模板规定的全部计算规则：涨跌幅 / 振幅 / COMEX 换算元克 / 夜盘变动 /
       千分位 / 日期与星期格式
    5. 生成报告 Markdown 骨架：build_markdown()；可选渲染 A4 PDF：render_pdf()
    6. 命令行入口：--demo 试跑，--config 读 JSON 配置，--prompt/--md/--pdf 分别导出

命令行用法
    python gold_price_report.py --demo
    python gold_price_report.py --report-date 2026-09-07 --data-date 2026-09-05 \
        --output-date 2026-09-08 --time 09:00 --dept 中国珠宝电子商务部 --fx 6.72
    python gold_price_report.py --config config.json --prompt prompt.txt --pdf report.pdf

依赖
    核心功能仅使用标准库；PDF 渲染为可选能力，需要 pip install reportlab
    （未安装时自动降级为只输出 Prompt 与 Markdown，不会报错）

把本文件重命名为 app.py 即可作为 GitHub 仓库入口直接运行。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

__version__ = '1.0.0'
__all__ = [
    'ReportConfig', 'ReportData', 'build_prompt', 'build_markdown', 'render_pdf',
    'pct_change', 'amplitude', 'comex_to_cny_per_gram', 'night_change',
    'thousand_sep', 'format_date', 'weekday_cn', 'quality_check', 'write_config_example',
]

# ---------------------------------------------------------------------------
# 一、角色与任务定位（模板第一节）
# ---------------------------------------------------------------------------
ROLE_PROMPT = """你是一名资深贵金属行业分析师、专业PDF文档制作师，隶属于【{dept}】。
请根据公开市场数据，生成一份《金价每日速报》PDF报告和小结，具体要求如下：
要求：
1. 所有数据必须来自公开可查渠道，禁止编造；无法核实的数据标注"待核实"或"估算"。
2. 严格按照下方四大板块结构输出，不得遗漏。
3. 语言风格：专业、简洁、数据驱动，避免主观臆断；关键结论需有数据支撑。
4. 最终交付PDF文件，中文字体清晰，表格排版整齐，必须两端对齐。
5. 附加交付趋势报告（长图）和基于此报告我该如何进行黄金原料采购的操作的文本小结
   （直接对话框文本：一、今日市场核心要点　二、未来七天关键变量分析
   　三、黄金原料采购操作建议：1.短期策略　2.中期策略　3.风控要点
   　最后添加风险提示：以上内容仅供参考，投资有风险，入市需谨慎。）"""

# ---------------------------------------------------------------------------
# 二、数据来源规范（模板第二节，必须交叉验证）
# ---------------------------------------------------------------------------
DATA_SOURCES: List[Tuple[int, str]] = [
    (1, '上海黄金交易所官网（sge.com.cn）延时行情/历史行情数据 —— '
        'Au99.99、Au(T+D)、Ag(T+D)的开盘/最高/最低/收盘'),
    (2, '汇通财经/金十数据官网/同花顺金融数据库/东方财富 —— 国际金价、COMEX期货'),
    (3, '新浪财经、每经AI、汇通财经、金投网、金价查询网 —— '
        '宏观事件、机构观点、夜盘数据、走势分析、多空力量、恐慌指数'),
    (4, '工商银行/建设银行等银行官网 —— 投资金条报价'),
    (5, '牧航农业、七里河发布等行业渠道 —— 水贝批发价、品牌金饰价'),
]

CROSS_VALIDATION_RULES: List[str] = [
    '同一数据至少2个来源一致方可采用；不一致时取上海黄金交易所/金投网/汇通财经/'
    '金十数据/同花顺官方数据为准，并在备注中说明差异。',
    '夜盘数据来源标注"上海黄金交易所行情/金投网/金十数据/工商银行延时行情及'
    '汇通财经等相关网站交叉验证"。',
    '成交量为双向计量，需在注释中说明。',
]

# ---------------------------------------------------------------------------
# 三、报告头部（模板第三节，固定格式）
# ---------------------------------------------------------------------------
HEADER_TEMPLATE = (
    '金价每日速报 | {report_date}\n'
    '数据统计时间：{data_date}（{weekday}, SGE正常交易日; 夜盘属{output_date}交易日）\n'
    '报告生成时间：{report_date} {gen_time}\n'
    '数据来源：上海黄金交易所官网延时行情、金融界、新浪财经、每经AI、金投网、'
    '金价查询网、21世纪经济报道、汇通财经、金十数据等'
)

# ---------------------------------------------------------------------------
# 四、板块详细指令（模板第四节，五大板块，原文完整转录）
# ---------------------------------------------------------------------------
SECTION_PROMPTS: Dict[str, str] = {}

SECTION_PROMPTS['板块一：国际金价'] = """【输出内容】
1. 表格（4列）：
   | 品种 | 价格(美元/盎司) | 涨跌幅 | 备注 |
   - 伦敦金现货：纽约尾盘收盘价，盘中区间（最低~最高），简要分析
     （备注的文字自动换行，不能溢出表格，15字以内）
   - COMEX黄金期货(12月合约)：收盘价，盘中高点/低点，本周累计涨跌幅（文字自动换行）
   - COMEX黄金(换算)：按在岸收盘汇率换算为元/克，标注汇率值（文字自动换行）
2. 关键事件段落（以"[!]关键事件:"开头，红色/加粗高亮）：
   - 当日影响金价的核心宏观事件（如非农数据、CPI、实际利率、生产指数、消费指数、
     美联储讲话、地缘冲突等）
   - 数据具体数值（实际值 vs 预期值 vs 前值）
   - 事件发生后金价的即时反应（从多少跌至/涨至多少）
   - 对美联储政策预期的影响（如加息概率从X%升至Y%）
   - 美元指数、美债收益率的联动方向
【数据要求】
- 伦敦金收盘价精确到小数点后2位
- 涨跌幅保留2位小数，带正负号
- 汇率取当日在岸人民币收盘价，标注具体数值"""

SECTION_PROMPTS['板块二：上海黄金交易所价格'] = """【输出内容】
分为"日盘数据"和"夜盘数据"两部分。
▎日盘数据（{prev_trade_date} 9:00-15:30）
1. 表格（7列）：
   | 品种 | 开盘价 | 最高价 | 最低价 | 收盘价 | 涨跌(元) | 涨跌幅 |
   品种包括：Au99.99、Au(T+D)、Ag(T+D)
2. 重点关注段落（以"★重点关注:"开头）：
   - Au99.99收盘价、盘中最高/最低、振幅
   - Au(T+D)成交量变化（较前日放量/缩量）
   - 日盘整体走势描述（受什么因素影响，盘中关键点位）
   - 白银Ag(T+D)收盘价及涨跌幅、盘中高低点
▎夜盘数据（{prev_trade_date}20:00—{data_date}02:30, 属{output_date}交易日, 归属下个交易日清算）
1. 表格（5列）：
   | 品种 | 夜盘最新价 | 夜盘最高 | 夜盘最低 | 较日盘收盘变动 |
   品种包括：Au99.99、Au(T+D)、Ag(T+D)
   - "较日盘收盘变动"同时显示绝对值和百分比，如 -12(-1.24%)
2. 夜盘解读段落（以"◆夜盘解读:"开头）：
   - 夜盘核心驱动因素（国际市场走势、数据公布等）
   - Au99.99、Au(T+D)夜盘波动区间及关键点位反应
   - 白银夜盘表现
   - 美元指数、加息预期变化
   - 市场静待的下一关键数据
▎注释（2条，小字灰色）：
注1：SGE日盘数据包含前一交易日夜盘与当日日盘合并计算，成交量为双向计量。
注2：夜盘数据来源上海黄金交易所延时行情及汇通财经、金投网交叉验证；
     夜盘涨跌幅以日盘收盘价为基准计算；持仓数据暂未更新，沿用日盘数据。
【数据要求】
- 所有价格精确到小数点后2位（Ag(T+D)取整数）
- 涨跌幅带正负号
- 成交量带千分位逗号
- 持仓数据带千分位逗号"""

SECTION_PROMPTS['板块三：竞品零售报价对比'] = """【输出内容】
分为"足金饰品"和"投资金条"两部分，最后附价差分析。
▎足金饰品（单位：元/克，{data_date}白天报价）
数据来源标注：牧航农业、金价查询网、同花顺金融数据库（{data_date}）
1. 表格（4列）：
   | 品牌 | 今日报价 | 较前日涨跌 | 备注 |
   品牌清单（按价格从高到低排列）：
   - 老凤祥、周大福、周大生、周生生、金至尊、潮宏基、谢瑞麟、六福珠宝、周六福、
     老庙黄金、中国黄金、水贝市场
   - 当日最高品牌在备注中标"当日最高"
   - 中国黄金备注"平价品牌"
   - 水贝市场备注"批发参考价(首饰金)"
▎投资金条（单位：元/克，{data_date}）
1. 表格（3列）：
   | 渠道/品牌 | 价格 | 涨跌 |
   渠道清单：
   - 中国黄金(投资金条)、菜百首饰(投资金条)、工商银行(如意金条)、建设银行(龙鼎金条)、
     中国银行(投资金条)、农业银行(传世之宝)、交通银行、招商银行、平安银行、中信银行、
     兴业银行、民生银行、浦发银行、周大福(投资金条)
   - 无数据的填"—"
▎价差分析（以"￭价差分析(基于{data_date}数据):"开头）：
计算并列出以下三组价差：
1. 品牌金饰(最高价~最低价) vs 投资金条(最低价~最高价)：价差X~Y元/克
2. 水贝批发价 vs 品牌零售(最高价~最低价)：品牌溢价X~Y元/克
3. 品牌金饰(最高价~最低价) vs 原料价Au99.99(收盘价)：溢价X~Y元/克
【数据要求】
- 品牌金饰价格取整数元/克
- 投资金条价格精确到小数点后2位
- 较前日涨跌带正负号，无数据填"—"
- 品牌顺序严格按当日报价从高到低排列"""

SECTION_PROMPTS['板块四：风险提示与金价影响因素分析'] = """【输出内容】
分为"风险等级"、"宏观因素分析"、"技术面关键位"、"短期预判"四部分。
▎风险等级
1. 表格（2列）：
   | 风险等级 | 内容 |
   风险等级分为三级：需关注（字体红色加粗）、持续跟踪（字体橙色加粗）、平稳（字体绿色加粗）
   每条内容包含：具体事件/数据 + 影响程度 + 关键时间节点
   典型条目示例：
   - 需关注：美国X月非农/ CPI超预期，加息预期升至X%，美联储X月X日议息会议为关键节点
   - 需关注：金价单日振幅超X美元，SGE夜盘Au(T+D)振幅X元/克，波动率显著放大
   - 需关注：地缘冲突（美伊/俄乌等），原油价格，地缘溢价
   - 持续跟踪：下一关键数据（具体日期+数据名称+预期值）
   - 平稳：央行购金数据、结构性买盘、去美元化趋势等长期支撑因素
▎宏观因素分析（4个子项，每项以"▶"开头的小标题 + 项目符号列表）
▶货币政策与利率
- 最新就业/通胀数据具体数值及与预期对比
- 平均时薪、失业率、劳动参与率等细分指标
- CME FedWatch加息概率变化（从X%升至Y%）
- 美联储官员讲话要点（鸽派/鹰派）
- 美元指数、10年期美债收益率走势
▶通胀与经济数据
- 就业数据的行业分布（哪些行业增/减）
- 制造业/服务业趋势
- 核心PCE/CPI当前水平及趋势
- 下一关键数据日期及预期值
▶地缘政治与避险
- 当前主要地缘冲突进展
- 对原油/航运的影响
- 各国央行黄金储备变动（从美国运回等）
- 去美元化趋势相关事件
▶央行购金与实物需求
- 世界黄金协会最新央行购金数据（吨数、同比增速）
- 机构仓位分析（裁量型买家仓位水平）
- 高盛/德银等对央行购金节奏的预测
▎技术面关键位
1. 表格（4列）：
   | 类型 | 位置 | 国际金价(美元/盎司) | 国内SGE(元/克) |
   包括：支撑1、支撑2、阻力1、阻力2、200日均线
   - 支撑1取近期夜盘/日内低点
   - 支撑2取前一周低点
   - 阻力1取近期高点
   - 阻力2取52周高点（标注日期）
   - 200日均线标注"已跌破/已站上"及具体位置
▎短期预判（以"▲短期预判(1-3天):"开头）
分三段：
1. 国际金价：预计X~Y美元区间震荡偏强/偏弱。核心逻辑。关键支撑/阻力位。
   跌破/突破后的下一目标位。
2. 国内SGE：Au99.99/Au(T+D)预估在X~Y元/克区间波动。关键支撑位。
3. 本周核心关注：具体数据名称+日期+两种情景分析
   （通胀降温→加息预期回落→金价反弹；通胀偏热→进一步承压）
最后附注释：200日均线位置估算说明。
【数据要求】
- 风险等级表格内容精炼，每条不少于20字且不超过50字
- 宏观因素每条项目符号开头，数据精确
- 技术面价格带千分位逗号
- 短期预判必须给出具体区间，不能模糊"""

SECTION_PROMPTS['板块五：机构观点'] = """【输出内容】
1. 表格（4列）：
   | 机构 | 短期观点 | 中长期目标价 | 核心逻辑 |
   机构清单（至少10家）：
   - 高盛、摩根士丹利、摩根大通、花旗、德意志银行、瑞银、法兴银行、
     RBC加拿大皇家银行、Amundi欧洲最大资管、富达国际、桥水·达利欧
   - 最后一行：世界黄金协会（内容为央行购金数据，目标价列留空）
   每列要求：
   - 短期观点：2-4字概括（战术谨慎/下半年看多/阶段性休整/拐点确认/稳健看好/
     重启多头/看多/已加仓/强烈建议等）
   - 中长期目标价：具体美元数值+时间点，如"4,900美元(2026年底)"
   - 核心逻辑：一句话概括该机构看多/看空的核心理由
2. 共识段落：
   - 中长期黄金结构性牛市的四大核心支柱
     （去美元化、美国财政赤字、央行储备多元化、私人资产低配黄金）
   - 短线影响因素及当前关键博弈区间
   - 机构年底目标价集中区间
   - 下一关键变量（数据+会议等信息）
【数据要求】
- 目标价带千分位逗号
- 机构观点必须来自近期（1个月内）公开研报/报道，禁止编造
- 如某机构最新观点无法核实，保留其上一次公开观点并在备注中说明"观点日期"
- 共识段落控制在20字以上200字以内，精炼有力（文字自动换行）"""

# ---------------------------------------------------------------------------
# 五、最后一页页脚（模板第五节，固定格式）
# ---------------------------------------------------------------------------
FOOTER_TEMPLATE = (
    '本报告由【{dept}】根据市场公开数据搜集整理生成 | {report_date} {gen_time}\n'
    '"以上内容仅供参考，投资有风险，入市需谨慎。"（居中）\n'
    '页码格式：- X -（居中，底部）'
)

RISK_NOTICE = '以上内容仅供参考，投资有风险，入市需谨慎。'

# ---------------------------------------------------------------------------
# 六、PDF 格式与排版规范（模板第六节）
# ---------------------------------------------------------------------------
PAGE_SETUP: Dict[str, Any] = {
    'paper': 'A4', 'width_mm': 210, 'height_mm': 297,
    'margin_top_mm': 15, 'margin_bottom_mm': 18,
    'margin_left_mm': 15, 'margin_right_mm': 15,
    'page_number': '底部居中，格式"- X -"',
}

FONT_SPEC: Dict[str, str] = {
    '标题': '黑体(SimHei) 18pt 居中 深蓝色 #1a3a5c',
    '板块标题': '黑体(SimHei) 13pt 白字+深蓝背景条 #2c5f8a',
    '子标题': '黑体(SimHei) 11pt 深蓝色',
    '正文': '仿宋(SimFang) 9.5pt 深灰 #222222 两端对齐',
    '表格内容': '仿宋(SimFang) 8.5pt（数据密集表格可用7.5pt）居中',
    '表格表头': '黑体(SimHei) 白字+深蓝背景',
    '注释': '仿宋(SimFang) 8pt 浅灰 #666666',
    '页脚': '仿宋(SimFang) 8pt 浅灰 #888888 居中',
}

TABLE_SPEC: Dict[str, str] = {
    '边框': '0.5pt 灰色 #d0d0d0',
    '表头背景': '深蓝色 #2c5f8a，白色字',
    '交替行背景': '浅灰色 #f0f0f0',
    '单元格内边距': '上下3pt，左右4pt',
    '数值对齐': '所有数值居中对齐',
    '表格对齐': '所有表格左右对齐',
}

MARKER_SPEC: Dict[str, str] = {
    '[!]': '关键事件，红色 #c0392b 加粗',
    '★': '重点关注前缀',
    '◆': '夜盘解读前缀',
    '￭': '价差分析前缀',
    '▲': '短期预判前缀',
    '▶': '宏观因素子项小标题前缀',
    '↑ / ↓': '上涨(红) / 下跌(绿)，或直接用文字"上涨/下跌"',
}

COLOR_SPEC: Dict[str, str] = {
    '上涨/红色': '#c0392b（关键事件、上涨箭头）',
    '下跌/绿色': '#27ae60（下跌箭头）',
    '主色调/深蓝': '#2c5f8a（表头、板块标题）',
    '辅助色/海军蓝': '#1a3a5c（大标题）',
    '灰色系': '#f0f0f0(交替行)、#d0d0d0(边框)、#666666(注释)、#888888(页脚)',
}

# 供 PDF 渲染直接取用的色值常量
COLOR_RISE = '#c0392b'
COLOR_FALL = '#27ae60'
COLOR_MAIN = '#2c5f8a'
COLOR_NAVY = '#1a3a5c'
COLOR_ALT_ROW = '#f0f0f0'
COLOR_BORDER = '#d0d0d0'
COLOR_NOTE = '#666666'
COLOR_FOOTER = '#888888'
COLOR_WARN = '#e67e22'
COLOR_BODY = '#222222'

FONT_TITLE = 'SimHei'
FONT_BODY = 'SimFang'

# ---------------------------------------------------------------------------
# 七、数据处理与计算规则（模板第七节）
# ---------------------------------------------------------------------------
CALC_RULES: List[str] = [
    '涨跌幅计算：(当日收盘价 - 前日收盘价) / 前日收盘价 * 100%，保留2位小数',
    '振幅计算：(最高价 - 最低价) / 前日收盘价 * 100%，保留2位小数',
    'COMEX换算人民币：COMEX价格(美元/盎司) / 31.1035 * 在岸汇率 = 元/克',
    '较日盘变动（夜盘）：夜盘最新价 - 日盘收盘价，同时计算百分比',
    '千分位：所有>=1000的数字加千分位逗号（如16,280、2,875,400）',
    '日期格式：统一使用"YYYY-MM-DD"，星期用中文（周五、周一等）',
    '时间节点：北京时间标注，美国数据标注公布时间（北京时间）',
]

TROY_OZ_IN_GRAM = 31.1035  # 1 金衡盎司 = 31.1035 克

# ---------------------------------------------------------------------------
# 八、质量检查清单（模板第八节，生成后逐项核对）
# ---------------------------------------------------------------------------
QUALITY_CHECKLIST: List[str] = [
    '板块齐全，各板块连续流畅阅读，无遗漏，每个板块内容要连接上个板块，版面连续，'
    '新板块不能另起一页，版面美化，不能出现文字穿插，全文表格必须左右对齐',
    '所有数据有公开来源支撑，无编造',
    '国际金价、SGE日盘/夜盘',
    '涨跌幅计算正确，正负号无误',
    '表格列数与模板一致，无错列',
    '关键事件包含具体数值（实际vs预期vs前值）',
    '短期预判给出具体价格区间，非模糊表述',
    '机构观点至少10家，目标价有具体数值和时间',
    '注释完整（SGE计量规则、夜盘归属、数据来源）',
    '中文字体显示正常，无乱码',
    '表格排版必须整齐，文字必须无溢出，溢出部分自动换行',
    '页码正确',
    '页脚部门名称和日期正确',
]

# ---------------------------------------------------------------------------
# 九、可调整变量速查表（模板第九节）
# ---------------------------------------------------------------------------
VARIABLE_TABLE: List[Tuple[str, str, str]] = [
    ('report_date / 报告日期', '报告发布当天', '2026-09-07'),
    ('data_date / 数据截止日', '上一个SGE交易日', '2026-09-05'),
    ('output_date / 下一交易日', '夜盘归属日', '2026-09-08'),
    ('gen_time / 生成时间', '报告生成时刻', '09:00'),
    ('dept / 部门名称', '出具部门', '中国珠宝电子商务部'),
    ('fx_rate / 在岸汇率', 'COMEX换算用', '6.72'),
    ('key_data / 关键数据日期', '下周CPI/PPI等', '9月10日PPI、9月11日CPI'),
    ('fomc_date / FOMC会议日期', '下次议息会议', '9月15-16日'),
]

BRAND_LIST: List[str] = ['老凤祥', '周大福', '周大生', '周生生', '金至尊', '潮宏基',
                         '谢瑞麟', '六福珠宝', '周六福', '老庙黄金', '中国黄金', '水贝市场']

BULLION_LIST: List[str] = ['中国黄金(投资金条)', '菜百首饰(投资金条)', '工商银行(如意金条)',
                           '建设银行(龙鼎金条)', '中国银行(投资金条)', '农业银行(传世之宝)',
                           '交通银行', '招商银行', '平安银行', '中信银行', '兴业银行',
                           '民生银行', '浦发银行', '周大福(投资金条)']

INSTITUTION_LIST: List[str] = ['高盛', '摩根士丹利', '摩根大通', '花旗', '德意志银行', '瑞银',
                               '法兴银行', 'RBC加拿大皇家银行', 'Amundi欧洲最大资管',
                               '富达国际', '桥水·达利欧', '世界黄金协会']

SGE_PRODUCTS: List[str] = ['Au99.99', 'Au(T+D)', 'Ag(T+D)']

TECH_LEVELS: List[str] = ['支撑1', '支撑2', '阻力1', '阻力2', '200日均线']

RISK_LEVELS: List[str] = ['需关注', '持续跟踪', '平稳']

# ===========================================================================
# 计算规则实现（严格对应模板第七节）
# ===========================================================================
def pct_change(close: float, prev_close: float, digits: int = 2, signed: bool = True) -> str:
    """涨跌幅：(当日收盘价 - 前日收盘价) / 前日收盘价 * 100%，保留 2 位小数。"""
    if prev_close in (0, None) or close is None:
        return '—'
    value = (close - prev_close) / prev_close * 100.0
    return f'{value:+.{digits}f}%' if signed else f'{value:.{digits}f}%'


def amplitude(high: float, low: float, prev_close: float, digits: int = 2) -> str:
    """振幅：(最高价 - 最低价) / 前日收盘价 * 100%，保留 2 位小数。"""
    if prev_close in (0, None) or high is None or low is None:
        return '—'
    value = (high - low) / prev_close * 100.0
    return f'{value:.{digits}f}%'


def comex_to_cny_per_gram(price_usd_oz: float, fx_rate: float, digits: int = 2) -> float:
    """COMEX 换算人民币：美元/盎司 ÷ 31.1035 × 在岸汇率 = 元/克。"""
    if price_usd_oz is None or not fx_rate:
        raise ValueError('COMEX 价格与在岸汇率均不可为空')
    return round(price_usd_oz / TROY_OZ_IN_GRAM * fx_rate, digits)


def night_change(night_last: float, day_close: float, digits: int = 2) -> str:
    """夜盘较日盘收盘变动：绝对值(百分比)，如 -12(-1.24%)。"""
    if night_last is None or day_close in (0, None):
        return '—'
    diff = night_last - day_close
    ratio = diff / day_close * 100.0
    return f'{diff:+.{digits}f}({ratio:+.{digits}f}%)'


def thousand_sep(value: Any) -> str:
    """千分位：所有 >=1000 的数字加千分位逗号（如 16,280、2,875,400）。"""
    if value is None or value == '':
        return '—'
    if isinstance(value, str):
        return value
    if isinstance(value, float) and float(value).is_integer():
        value = int(value)
    text = f'{value:,}'
    return text


def signed(value: Any, digits: int = 2) -> str:
    """带正负号的涨跌显示，无数据填破折号。"""
    if value is None or value == '':
        return '—'
    return f'{float(value):+.{digits}f}'


_WEEKDAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def weekday_cn(date_str: str) -> str:
    """把 YYYY-MM-DD 转成中文星期（周五、周一等）。"""
    return _WEEKDAY_CN[_parse_date(date_str).weekday()]


def format_date(date_str: str) -> str:
    """规范化日期为 YYYY-MM-DD。"""
    return _parse_date(date_str).strftime('%Y-%m-%d')


def _parse_date(date_str: str) -> '_dt.date':
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%Y.%m.%d'):
        try:
            return _dt.datetime.strptime(str(date_str).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f'无法解析日期：{date_str}（要求 YYYY-MM-DD）')


def prev_trading_day(date_str: str) -> str:
    """回退到上一个工作日（简单口径，不考虑法定节假日）。"""
    d = _parse_date(date_str)
    d -= _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def next_trading_day(date_str: str) -> str:
    """推进到下一个工作日（简单口径，不考虑法定节假日）。"""
    d = _parse_date(date_str)
    d += _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += _dt.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


# ===========================================================================
# 配置与数据结构
# ===========================================================================
@dataclass
class ReportConfig:
    """模板第九节「可调整变量速查表」的参数化载体。"""
    report_date: str = field(default_factory=lambda: _dt.date.today().strftime('%Y-%m-%d'))
    data_date: str = ''
    output_date: str = ''
    prev_trade_date: str = ''
    gen_time: str = field(default_factory=lambda: _dt.datetime.now().strftime('%H:%M'))
    dept: str = '中国珠宝电子商务部'
    fx_rate: float = 6.72
    key_data: str = '待核实'
    fomc_date: str = '待核实'
    trend_image: str = ''   # 趋势长图路径（可选，插入 PDF）
    extra_notes: str = ''   # 附加说明（可选，追加到 Prompt 末尾）

    def __post_init__(self) -> None:
        if not self.data_date:
            self.data_date = prev_trading_day(self.report_date)
        if not self.prev_trade_date:
            self.prev_trade_date = prev_trading_day(self.data_date)
        if not self.output_date:
            self.output_date = next_trading_day(self.data_date)
        self.report_date = format_date(self.report_date)
        self.data_date = format_date(self.data_date)
        self.output_date = format_date(self.output_date)
        self.prev_trade_date = format_date(self.prev_trade_date)

    # --- 派生字段 ---
    @property
    def weekday(self) -> str:
        return weekday_cn(self.data_date)

    def fmt_map(self) -> Dict[str, str]:
        """供模板字符串 format 使用的变量字典。"""
        return {
            'report_date': self.report_date,
            'data_date': self.data_date,
            'output_date': self.output_date,
            'prev_trade_date': self.prev_trade_date,
            'gen_time': self.gen_time,
            'dept': self.dept,
            'weekday': self.weekday,
            'fx_rate': f'{self.fx_rate:.4f}'.rstrip('0').rstrip('.'),
            'key_data': self.key_data,
            'fomc_date': self.fomc_date,
        }

    @classmethod
    def from_json(cls, path: str) -> 'ReportConfig':
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        allowed = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**allowed)

    def to_json(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)


@dataclass
class ReportData:
    """报告正文数据容器。字段值统一用 dict/list 承载，None 表示待核实。

    示例
        ReportData(
            intl=[{'name': '伦敦金现货', 'price': 3612.50, 'chg': '+0.82%',
                   'note': '纽约尾盘反弹'}],
            sge_day=[{'name': 'Au99.99', 'open': 771.5, 'high': 778.2,
                      'low': 769.8, 'close': 776.4, 'prev_close': 773.1}],
            brands=[{'brand': '老凤祥', 'price': 1058, 'chg': 6}],
            bullion=[{'name': '中国黄金(投资金条)', 'price': 792.35, 'chg': 3.2}],
            institutions=[{'org': '高盛', 'view': '下半年看多',
                           'target': '4,900美元(2026年底)', 'logic': '央行持续购金'}],
        )
    """
    intl: List[Dict[str, Any]] = field(default_factory=list)
    sge_day: List[Dict[str, Any]] = field(default_factory=list)
    sge_night: List[Dict[str, Any]] = field(default_factory=list)
    brands: List[Dict[str, Any]] = field(default_factory=list)
    bullion: List[Dict[str, Any]] = field(default_factory=list)
    risk: List[Dict[str, Any]] = field(default_factory=list)
    tech: List[Dict[str, Any]] = field(default_factory=list)
    institutions: List[Dict[str, Any]] = field(default_factory=list)
    key_events: str = ''
    focus_note: str = ''
    night_note: str = ''
    spread_note: str = ''
    short_term: str = ''
    consensus: str = ''

    @classmethod
    def from_json(cls, path: str) -> 'ReportData':
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        allowed = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**allowed)


# ===========================================================================
# Prompt 构建：把模板还原成可下达给 AI 的完整指令文本
# ===========================================================================
def build_prompt(cfg: ReportConfig, data: Optional[ReportData] = None) -> str:
    """组装完整 Prompt（模板第一至九节的程序化还原）。"""
    m = cfg.fmt_map()
    out: List[str] = []
    out.append('=' * 72)
    out.append('《金价每日速报》生成指令（由 gold_price_report.py 自动装配）')
    out.append('=' * 72)

    out.append('\n【一、角色与任务定位】')
    out.append(ROLE_PROMPT.format(**m))

    out.append('\n【二、数据来源规范（必须交叉验证）】')
    out.append('数据来源优先级（从高到低）：')
    for level, desc in DATA_SOURCES:
        out.append(f'  {level}. {desc}')
    out.append('交叉验证规则：')
    for rule in CROSS_VALIDATION_RULES:
        out.append(f'  - {rule}')

    out.append('\n【三、报告头部（固定格式）】')
    out.append(HEADER_TEMPLATE.format(**m))

    out.append('\n【四、板块详细指令】')
    for title, body in SECTION_PROMPTS.items():
        out.append('\n--- ' + title + ' ---')
        out.append(body.format(**m))

    out.append('\n【五、最后一页页脚（固定格式）】')
    out.append(FOOTER_TEMPLATE.format(**m))

    out.append('\n【六、PDF格式与排版规范】')
    out.append('页面设置：')
    out.append(f"  纸张：{PAGE_SETUP['paper']}（{PAGE_SETUP['width_mm']}mm × "
               f"{PAGE_SETUP['height_mm']}mm）；上边距{PAGE_SETUP['margin_top_mm']}mm、"
               f"下边距{PAGE_SETUP['margin_bottom_mm']}mm、"
               f"左右边距{PAGE_SETUP['margin_left_mm']}mm；页码：{PAGE_SETUP['page_number']}")
    out.append('字体：')
    for k, v in FONT_SPEC.items():
        out.append(f'  - {k}：{v}')
    out.append('表格样式：')
    for k, v in TABLE_SPEC.items():
        out.append(f'  - {k}：{v}')
    out.append('特殊标记：')
    for k, v in MARKER_SPEC.items():
        out.append(f'  - {k}：{v}')
    out.append('颜色规范：')
    for k, v in COLOR_SPEC.items():
        out.append(f'  - {k}：{v}')

    out.append('\n【七、数据处理与计算规则】')
    for i, rule in enumerate(CALC_RULES, 1):
        out.append(f'  {i}. {rule}')
    out.append(f'  换算常数：1 金衡盎司 = {TROY_OZ_IN_GRAM} 克')
    out.append(f'  本期在岸汇率：{m["fx_rate"]}')

    out.append('\n【八、质量检查清单（生成后必须逐项核对）】')
    for item in QUALITY_CHECKLIST:
        out.append('  □ ' + item)

    out.append('\n【九、本期已填充变量】')
    for k, v in m.items():
        out.append(f'  {k} = {v}')

    if data is not None:
        out.append('\n【十、本期已采集数据（供直接排版，缺失项请标注"待核实"）】')
        out.append(_dump_data(data, cfg))

    if cfg.extra_notes:
        out.append('\n【附加要求】')
        out.append(cfg.extra_notes)

    return '\n'.join(out)


def _dump_data(data: ReportData, cfg: ReportConfig) -> str:
    lines: List[str] = []
    if data.intl:
        lines.append('国际金价：')
        for r in data.intl:
            lines.append(f"  {r.get('name', '—')} | {r.get('price', '—')} | "
                         f"{r.get('chg', '—')} | {r.get('note', '—')}")
    if data.sge_day:
        lines.append('SGE日盘：')
        for r in data.sge_day:
            lines.append(f"  {r.get('name', '—')} 开{r.get('open', '—')} 高{r.get('high', '—')} "
                         f"低{r.get('low', '—')} 收{r.get('close', '—')} "
                         f"涨跌{signed(r.get('diff'))} 涨跌幅{pct_change(r.get('close'), r.get('prev_close'))}")
    if data.sge_night:
        lines.append('SGE夜盘：')
        for r in data.sge_night:
            chg = r.get('chg') or night_change(r.get('last'), r.get('day_close'))
            lines.append(f"  {r.get('name', '—')} 最新{r.get('last', '—')} 高{r.get('high', '—')} "
                         f"低{r.get('low', '—')} 较日盘{chg}")
    if data.brands:
        lines.append('足金饰品（需按报价从高到低排列）：')
        for r in data.brands:
            lines.append(f"  {r.get('brand', '—')} {r.get('price', '—')} "
                         f"{signed(r.get('chg'), 0)} {r.get('note', '—')}")
    if data.bullion:
        lines.append('投资金条：')
        for r in data.bullion:
            lines.append(f"  {r.get('name', '—')} {thousand_sep(r.get('price'))} "
                         f"{signed(r.get('chg'))}")
    if data.risk:
        lines.append('风险等级：')
        for r in data.risk:
            lines.append(f"  [{r.get('level', '需关注')}] {r.get('content', '—')}")
    if data.tech:
        lines.append('技术面关键位：')
        for r in data.tech:
            lines.append(f"  {r.get('type', '—')} {r.get('pos', '—')} "
                         f"{thousand_sep(r.get('intl'))} {thousand_sep(r.get('sge'))}")
    if data.institutions:
        lines.append(f'机构观点（模板要求至少10家，本期 {len(data.institutions)} 家）：')
        for r in data.institutions:
            lines.append(f"  {r.get('org', '—')} | {r.get('view', '—')} | "
                         f"{r.get('target', '—')} | {r.get('logic', '—')}")
    for label, text in (('[!]关键事件', data.key_events), ('★重点关注', data.focus_note),
                        ('◆夜盘解读', data.night_note), ('￭价差分析', data.spread_note),
                        ('▲短期预判', data.short_term), ('机构共识', data.consensus)):
        if text:
            lines.append(f'{label}: {text}')
    if not lines:
        lines.append('  （未提供数据，全部字段需按"待核实"处理）')
    return '\n'.join(lines)

# ===========================================================================
# Markdown 报告骨架：把板块结构落成可填写的表格
# ===========================================================================
def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join(['---'] * len(headers)) + '|']
    for r in rows:
        out.append('| ' + ' | '.join('—' if c is None or c == '' else str(c) for c in r) + ' |')
    return out


def build_markdown(cfg: ReportConfig, data: Optional[ReportData] = None) -> str:
    """生成报告 Markdown（表头与模板规定的列数严格一致，便于直接核对）。"""
    m = cfg.fmt_map()
    d = data or ReportData()
    out: List[str] = []
    out.append(f"# 金价每日速报 | {m['report_date']}")
    out.append('')
    out.append(f"- 数据统计时间：{m['data_date']}（{m['weekday']}, SGE正常交易日; "
               f"夜盘属{m['output_date']}交易日）")
    out.append(f"- 报告生成时间：{m['report_date']} {m['gen_time']}")
    out.append('- 数据来源：上海黄金交易所官网延时行情、金融界、新浪财经、每经AI、金投网、'
               '金价查询网、21世纪经济报道、汇通财经、金十数据等')
    out.append('')

    # 板块一
    out.append('## 板块一：国际金价')
    out.append('')
    rows = [[r.get('name'), thousand_sep(r.get('price')), r.get('chg'), r.get('note')]
            for r in d.intl] or [['伦敦金现货', None, None, None],
                                 ['COMEX黄金期货(12月合约)', None, None, None],
                                 ['COMEX黄金(换算)', None, None, f'按汇率{m["fx_rate"]}换算']]
    out += _md_table(['品种', '价格(美元/盎司)', '涨跌幅', '备注'], rows)
    out.append('')
    if d.key_events:
        out.append(f'**[!]关键事件:** {d.key_events}')
        out.append('')

    # 板块二
    out.append('## 板块二：上海黄金交易所价格')
    out.append('')
    out.append(f"### ▎日盘数据（{m['prev_trade_date']} 9:00-15:30）")
    out.append('')
    day_rows = []
    for r in d.sge_day:
        day_rows.append([r.get('name'), r.get('open'), r.get('high'), r.get('low'),
                         r.get('close'), signed(r.get('diff')),
                         pct_change(r.get('close'), r.get('prev_close'))])
    if not day_rows:
        day_rows = [[p, None, None, None, None, None, None] for p in SGE_PRODUCTS]
    out += _md_table(['品种', '开盘价', '最高价', '最低价', '收盘价', '涨跌(元)', '涨跌幅'], day_rows)
    out.append('')
    if d.focus_note:
        out.append(f'**★重点关注:** {d.focus_note}')
        out.append('')
    out.append(f"### ▎夜盘数据（{m['prev_trade_date']}20:00—{m['data_date']}02:30, "
               f"属{m['output_date']}交易日）")
    out.append('')
    night_rows = []
    for r in d.sge_night:
        night_rows.append([r.get('name'), r.get('last'), r.get('high'), r.get('low'),
                           r.get('chg') or night_change(r.get('last'), r.get('day_close'))])
    if not night_rows:
        night_rows = [[p, None, None, None, None] for p in SGE_PRODUCTS]
    out += _md_table(['品种', '夜盘最新价', '夜盘最高', '夜盘最低', '较日盘收盘变动'], night_rows)
    out.append('')
    if d.night_note:
        out.append(f'**◆夜盘解读:** {d.night_note}')
        out.append('')
    out.append('> 注1：SGE日盘数据包含前一交易日夜盘与当日日盘合并计算，成交量为双向计量。')
    out.append('> ')
    out.append('> 注2：夜盘数据来源上海黄金交易所延时行情及汇通财经、金投网交叉验证；'
               '夜盘涨跌幅以日盘收盘价为基准计算；持仓数据暂未更新，沿用日盘数据。')
    out.append('')

    # 板块三
    out.append('## 板块三：竞品零售报价对比')
    out.append('')
    out.append(f"### ▎足金饰品（元/克，{m['data_date']}白天报价）")
    out.append('')
    out.append(f'数据来源标注：牧航农业、金价查询网、同花顺金融数据库（{m["data_date"]}）')
    out.append('')
    brand_src = sorted(d.brands, key=lambda r: float(r.get('price') or 0), reverse=True) \
        if d.brands else [{'brand': b} for b in BRAND_LIST]
    b_rows = []
    top_price = max((float(r.get('price') or 0) for r in brand_src), default=0)
    for r in brand_src:
        brand = r.get('brand', '—')
        note = r.get('note') or ''
        if not note:
            if brand == '中国黄金':
                note = '平价品牌'
            elif brand == '水贝市场':
                note = '批发参考价(首饰金)'
            elif top_price and float(r.get('price') or 0) == top_price:
                note = '当日最高'
        b_rows.append([brand, r.get('price'), signed(r.get('chg'), 0), note])
    out += _md_table(['品牌', '今日报价', '较前日涨跌', '备注'], b_rows)
    out.append('')
    out.append(f"### ▎投资金条（元/克，{m['data_date']}）")
    out.append('')
    bull_src = d.bullion or [{'name': n} for n in BULLION_LIST]
    u_rows = [[r.get('name'), thousand_sep(r.get('price')), signed(r.get('chg'))]
              for r in bull_src]
    out += _md_table(['渠道/品牌', '价格', '涨跌'], u_rows)
    out.append('')
    if d.spread_note:
        out.append(f'**￭价差分析(基于{m["data_date"]}数据):** {d.spread_note}')
        out.append('')

    # 板块四
    out.append('## 板块四：风险提示与金价影响因素分析')
    out.append('')
    out.append('### ▎风险等级')
    out.append('')
    r_rows = [[r.get('level', '需关注'), r.get('content')] for r in d.risk] or \
             [[lv, None] for lv in RISK_LEVELS]
    out += _md_table(['风险等级', '内容'], r_rows)
    out.append('')
    out.append('### ▎宏观因素分析')
    out.append('')
    for sub in ('货币政策与利率', '通胀与经济数据', '地缘政治与避险', '央行购金与实物需求'):
        out.append(f'▶{sub}')
        out.append('')
        out.append('- 待填（须含具体数值、与预期对比、时间节点）')
        out.append('')
    out.append('### ▎技术面关键位')
    out.append('')
    t_rows = [[r.get('type'), r.get('pos'), thousand_sep(r.get('intl')), thousand_sep(r.get('sge'))]
              for r in d.tech] or [[lv, None, None, None] for lv in TECH_LEVELS]
    out += _md_table(['类型', '位置', '国际金价(美元/盎司)', '国内SGE(元/克)'], t_rows)
    out.append('')
    if d.short_term:
        out.append(f'**▲短期预判(1-3天):** {d.short_term}')
        out.append('')

    # 板块五
    out.append('## 板块五：机构观点')
    out.append('')
    i_rows = [[r.get('org'), r.get('view'), r.get('target'), r.get('logic')]
              for r in d.institutions] or [[o, None, None, None] for o in INSTITUTION_LIST]
    out += _md_table(['机构', '短期观点', '中长期目标价', '核心逻辑'], i_rows)
    out.append('')
    if d.consensus:
        out.append(f'**机构共识:** {d.consensus}')
        out.append('')

    # 采购操作小结
    out.append('## 附：黄金原料采购操作小结')
    out.append('')
    out.append('### 一、今日市场核心要点')
    out.append('')
    out.append('### 二、未来七天关键变量分析')
    out.append('')
    out.append(f'关键数据：{m["key_data"]}；FOMC 议息会议：{m["fomc_date"]}')
    out.append('')
    out.append('### 三、黄金原料采购操作建议')
    out.append('')
    out.append('1. 短期策略：')
    out.append('2. 中期策略：')
    out.append('3. 风控要点：')
    out.append('')
    out.append(f'风险提示：{RISK_NOTICE}')
    out.append('')
    out.append(f"*本报告由【{m['dept']}】根据市场公开数据搜集整理生成 | "
               f"{m['report_date']} {m['gen_time']}*")
    return '\n'.join(out)


# ===========================================================================
# PDF 渲染（可选能力：未安装 reportlab 时自动降级）
# ===========================================================================
def _find_cjk_font(name: str) -> Optional[str]:
    """在常见位置寻找可用中文字体文件，返回路径或 None。"""
    candidates = [
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simfang.ttf',
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def render_pdf(cfg: ReportConfig, data: Optional[ReportData] = None,
               out_path: str = '金价每日速报.pdf') -> str:
    """按模板第六节排版规范渲染 A4 PDF；缺少 reportlab 时抛 RuntimeError。"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                        Paragraph, Spacer, Table, TableStyle,
                                        Image as RLImage)
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError('PDF 渲染需要 reportlab，请先执行 pip install reportlab') from exc

    m = cfg.fmt_map()
    d = data or ReportData()

    # 中文字体注册（优先系统黑体/仿宋，回退文泉驿/思源）
    title_font, body_font = FONT_TITLE, FONT_BODY
    heiti = _find_cjk_font('heiti')
    fangsong = _find_cjk_font('fangsong')
    fallback = heiti or fangsong
    if fallback:
        try:
            pdfmetrics.registerFont(TTFont('CJK', fallback, subfontIndex=0))
            title_font = body_font = 'CJK'
        except Exception:
            pass
    if not fallback:
        title_font = body_font = 'Helvetica'

    def _rgb(hex_str: str):
        return colors.HexColor(hex_str)

    page_w, page_h = A4
    ml, mr = PAGE_SETUP['margin_left_mm'] * mm, PAGE_SETUP['margin_right_mm'] * mm
    mt, mb = PAGE_SETUP['margin_top_mm'] * mm, PAGE_SETUP['margin_bottom_mm'] * mm

    st_title = ParagraphStyle('t', fontName=title_font, fontSize=18, leading=24,
                              alignment=TA_CENTER, textColor=_rgb(COLOR_NAVY))
    st_sec = ParagraphStyle('s', fontName=title_font, fontSize=13, leading=18,
                            textColor=colors.white, backColor=_rgb(COLOR_MAIN),
                            borderPadding=3, spaceBefore=8, spaceAfter=5)
    st_sub = ParagraphStyle('u', fontName=title_font, fontSize=11, leading=15,
                            textColor=_rgb(COLOR_MAIN), spaceBefore=5, spaceAfter=3)
    st_body = ParagraphStyle('b', fontName=body_font, fontSize=9.5, leading=14.5,
                             textColor=_rgb(COLOR_BODY), alignment=TA_JUSTIFY)
    st_mark = ParagraphStyle('m', parent=st_body, textColor=_rgb(COLOR_RISE),
                             fontName=title_font)
    st_note = ParagraphStyle('n', fontName=body_font, fontSize=8, leading=11,
                             textColor=_rgb(COLOR_NOTE))
    st_cell = ParagraphStyle('c', fontName=body_font, fontSize=8.5, leading=11,
                             alignment=TA_CENTER)

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(body_font, 8)
        canvas.setFillColor(_rgb(COLOR_FOOTER))
        canvas.drawCentredString(page_w / 2.0, 8 * mm,
                                 f'- {doc.page} -')
        canvas.drawString(ml, 13 * mm,
                          f"本报告由【{m['dept']}】根据市场公开数据搜集整理生成 | "
                          f"{m['report_date']} {m['gen_time']}")
        canvas.drawCentredString(page_w / 2.0, 4 * mm, RISK_NOTICE)
        canvas.restoreState()

    doc = BaseDocTemplate(out_path, pagesize=A4, leftMargin=ml, rightMargin=mr,
                          topMargin=mt, bottomMargin=mb,
                          title=f'金价每日速报 {m["report_date"]}', author=m['dept'])
    frame = Frame(ml, mb, page_w - ml - mr, page_h - mt - mb, id='f')
    doc.addPageTemplates([PageTemplate(id='p', frames=[frame], onPage=on_page)])

    def mk_table(headers, rows, widths=None, font_size=8.5):
        cell = ParagraphStyle('cc', parent=st_cell, fontSize=font_size)
        head = [Paragraph(f'<b>{h}</b>',
                          ParagraphStyle('h', parent=cell, fontName=title_font,
                                         textColor=colors.white, fontSize=font_size))
                for h in headers]
        body = [[Paragraph(str(c) if c not in (None, '') else '—', cell) for c in row]
                for row in rows]
        t = Table([head] + body, colWidths=widths, hAlign='LEFT', repeatRows=1)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), _rgb(COLOR_MAIN)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, _rgb(COLOR_BORDER)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(body) + 1):
            if i % 2 == 0:
                style.append(('BACKGROUND', (0, i), (-1, i), _rgb(COLOR_ALT_ROW)))
        t.setStyle(TableStyle(style))
        return t

    avail = page_w - ml - mr
    story: List[Any] = []
    story.append(Paragraph(f'金价每日速报 | {m["report_date"]}', st_title))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f'数据统计时间：{m["data_date"]}（{m["weekday"]}, SGE正常交易日; '
        f'夜盘属{m["output_date"]}交易日）　报告生成时间：{m["report_date"]} {m["gen_time"]}',
        st_note))
    story.append(Paragraph('数据来源：上海黄金交易所官网延时行情、金融界、新浪财经、每经AI、'
                           '金投网、金价查询网、21世纪经济报道、汇通财经、金十数据等', st_note))
    story.append(Spacer(1, 6))

    # 板块一
    story.append(Paragraph('板块一：国际金价', st_sec))
    intl_rows = [[r.get('name'), thousand_sep(r.get('price')), r.get('chg'), r.get('note')]
                 for r in d.intl] or [['伦敦金现货', None, None, None],
                                       ['COMEX黄金期货(12月合约)', None, None, None],
                                       ['COMEX黄金(换算)', None, None,
                                        f'按汇率{m["fx_rate"]}换算']]
    story.append(mk_table(['品种', '价格(美元/盎司)', '涨跌幅', '备注'], intl_rows,
                          [avail * w for w in (0.24, 0.18, 0.12, 0.46)]))
    if d.key_events:
        story.append(Paragraph(f'[!]关键事件: {d.key_events}', st_mark))

    # 板块二
    story.append(Paragraph('板块二：上海黄金交易所价格', st_sec))
    story.append(Paragraph(f"▎日盘数据（{m['prev_trade_date']} 9:00-15:30）", st_sub))
    day_rows = [[r.get('name'), r.get('open'), r.get('high'), r.get('low'), r.get('close'),
                 signed(r.get('diff')), pct_change(r.get('close'), r.get('prev_close'))]
                for r in d.sge_day] or [[p] + [None] * 6 for p in SGE_PRODUCTS]
    story.append(mk_table(['品种', '开盘价', '最高价', '最低价', '收盘价', '涨跌(元)', '涨跌幅'],
                          day_rows, [avail * w for w in (0.16, 0.14, 0.14, 0.14, 0.14, 0.14, 0.14)],
                          font_size=7.5))
    if d.focus_note:
        story.append(Paragraph(f'★重点关注: {d.focus_note}', st_body))
    story.append(Paragraph(f"▎夜盘数据（{m['prev_trade_date']}20:00—{m['data_date']}02:30, "
                           f"属{m['output_date']}交易日）", st_sub))
    night_rows = [[r.get('name'), r.get('last'), r.get('high'), r.get('low'),
                   r.get('chg') or night_change(r.get('last'), r.get('day_close'))]
                  for r in d.sge_night] or [[p] + [None] * 4 for p in SGE_PRODUCTS]
    story.append(mk_table(['品种', '夜盘最新价', '夜盘最高', '夜盘最低', '较日盘收盘变动'],
                          night_rows, [avail * w for w in (0.20, 0.20, 0.20, 0.20, 0.20)]))
    if d.night_note:
        story.append(Paragraph(f'◆夜盘解读: {d.night_note}', st_body))
    story.append(Paragraph('注1：SGE日盘数据包含前一交易日夜盘与当日日盘合并计算，成交量为双向计量。',
                           st_note))
    story.append(Paragraph('注2：夜盘数据来源上海黄金交易所延时行情及汇通财经、金投网交叉验证；'
                           '夜盘涨跌幅以日盘收盘价为基准计算；持仓数据暂未更新，沿用日盘数据。',
                           st_note))

    # 板块三
    story.append(Paragraph('板块三：竞品零售报价对比', st_sec))
    story.append(Paragraph(f"▎足金饰品（元/克，{m['data_date']}白天报价）", st_sub))
    brand_src = sorted(d.brands, key=lambda r: float(r.get('price') or 0), reverse=True) \
        if d.brands else [{'brand': b} for b in BRAND_LIST]
    top_price = max((float(r.get('price') or 0) for r in brand_src), default=0)
    b_rows = []
    for r in brand_src:
        brand = r.get('brand', '—')
        note = r.get('note') or ''
        if not note:
            if brand == '中国黄金':
                note = '平价品牌'
            elif brand == '水贝市场':
                note = '批发参考价(首饰金)'
            elif top_price and float(r.get('price') or 0) == top_price:
                note = '当日最高'
        b_rows.append([brand, r.get('price'), signed(r.get('chg'), 0), note])
    story.append(mk_table(['品牌', '今日报价', '较前日涨跌', '备注'], b_rows,
                          [avail * w for w in (0.22, 0.18, 0.18, 0.42)]))
    story.append(Paragraph(f"▎投资金条（元/克，{m['data_date']}）", st_sub))
    bull_src = d.bullion or [{'name': n} for n in BULLION_LIST]
    u_rows = [[r.get('name'), thousand_sep(r.get('price')), signed(r.get('chg'))]
              for r in bull_src]
    story.append(mk_table(['渠道/品牌', '价格', '涨跌'], u_rows,
                          [avail * w for w in (0.46, 0.27, 0.27)]))
    if d.spread_note:
        story.append(Paragraph(f'￭价差分析(基于{m["data_date"]}数据): {d.spread_note}', st_body))

    # 板块四
    story.append(Paragraph('板块四：风险提示与金价影响因素分析', st_sec))
    story.append(Paragraph('▎风险等级', st_sub))
    r_rows = [[r.get('level', '需关注'), r.get('content')] for r in d.risk] or \
             [[lv, None] for lv in RISK_LEVELS]
    story.append(mk_table(['风险等级', '内容'], r_rows,
                          [avail * w for w in (0.18, 0.82)]))
    story.append(Paragraph('▎宏观因素分析', st_sub))
    for sub in ('货币政策与利率', '通胀与经济数据', '地缘政治与避险', '央行购金与实物需求'):
        story.append(Paragraph(f'▶{sub}', st_sub))
        story.append(Paragraph('待填：须包含具体数值、与预期对比、关键时间节点。', st_body))
    story.append(Paragraph('▎技术面关键位', st_sub))
    t_rows = [[r.get('type'), r.get('pos'), thousand_sep(r.get('intl')), thousand_sep(r.get('sge'))]
              for r in d.tech] or [[lv, None, None, None] for lv in TECH_LEVELS]
    story.append(mk_table(['类型', '位置', '国际金价(美元/盎司)', '国内SGE(元/克)'], t_rows,
                          [avail * w for w in (0.18, 0.24, 0.29, 0.29)]))
    if d.short_term:
        story.append(Paragraph(f'▲短期预判(1-3天): {d.short_term}', st_body))

    # 板块五
    story.append(Paragraph('板块五：机构观点', st_sec))
    i_rows = [[r.get('org'), r.get('view'), r.get('target'), r.get('logic')]
              for r in d.institutions] or [[o, None, None, None] for o in INSTITUTION_LIST]
    story.append(mk_table(['机构', '短期观点', '中长期目标价', '核心逻辑'], i_rows,
                          [avail * w for w in (0.20, 0.15, 0.22, 0.43)], font_size=7.5))
    if d.consensus:
        story.append(Paragraph(f'机构共识: {d.consensus}', st_body))

    # 采购小结
    story.append(Paragraph('附：黄金原料采购操作小结', st_sec))
    for h in ('一、今日市场核心要点', '二、未来七天关键变量分析', '三、黄金原料采购操作建议'):
        story.append(Paragraph(h, st_sub))
    story.append(Paragraph(f'关键数据：{m["key_data"]}；FOMC 议息会议：{m["fomc_date"]}', st_body))
    story.append(Paragraph('1. 短期策略：待填　2. 中期策略：待填　3. 风控要点：待填', st_body))

    if cfg.trend_image and os.path.exists(cfg.trend_image):
        story.append(Paragraph('附：趋势报告（长图）', st_sec))
        try:
            story.append(RLImage(cfg.trend_image, width=avail, height=None))
        except Exception:
            pass

    doc.build(story)
    return out_path


# ===========================================================================
# 质检：对已填数据做模板规定的机械核对
# ===========================================================================
def quality_check(cfg: ReportConfig, data: ReportData) -> List[Tuple[bool, str]]:
    """返回 [(是否通过, 说明)]，对应模板第八节可自动判定的条目。"""
    res: List[Tuple[bool, str]] = []
    res.append((len(SECTION_PROMPTS) == 5,
                f'板块数量：{len(SECTION_PROMPTS)}（模板要求 5 个板块，模板原文称四大板块+机构观点）'))
    res.append((len(data.institutions) >= 10,
                f'机构观点数量：{len(data.institutions)}（要求至少10家）'))
    res.append((len(data.sge_day) == len(SGE_PRODUCTS),
                f'SGE日盘品种数：{len(data.sge_day)}（要求 {len(SGE_PRODUCTS)} 个）'))
    res.append((len(data.sge_night) == len(SGE_PRODUCTS),
                f'SGE夜盘品种数：{len(data.sge_night)}（要求 {len(SGE_PRODUCTS)} 个）'))
    res.append((bool(data.short_term), '短期预判是否给出（必须含具体价格区间）'))
    res.append((bool(data.key_events), '关键事件是否填写（须含实际值/预期值/前值）'))
    res.append((bool(data.spread_note), '价差分析是否填写（三组价差）'))
    missing = [b.get('brand') for b in data.brands if not b.get('price')]
    res.append((bool(data.brands) and not missing,
                f'品牌金饰报价完整性：缺 {missing if missing else "无"}'))
    prices = [float(b.get('price') or 0) for b in data.brands]
    sorted_ok = all(prices[i] >= prices[i + 1] for i in range(len(prices) - 1)) if len(prices) > 1 else True
    res.append((sorted_ok, '品牌顺序是否按报价从高到低排列'))
    bad_chg = [r.get('name') for r in data.sge_day
               if r.get('close') is not None and r.get('prev_close')
               and not str(pct_change(r.get('close'), r.get('prev_close'))).endswith('%')]
    res.append((not bad_chg, f'涨跌幅格式（2位小数带正负号）异常项：{bad_chg if bad_chg else "无"}'))
    res.append((bool(cfg.data_date and cfg.report_date), '报告头部日期完整性'))
    return res


def write_config_example(path: str) -> str:
    """导出一份 JSON 配置样例，便于命令行 --config 直接套用。"""
    cfg = ReportConfig(report_date='2026-09-07', data_date='2026-09-05',
                       output_date='2026-09-08', gen_time='09:00', fx_rate=6.72,
                       key_data='9月10日PPI、9月11日CPI', fomc_date='9月15-16日')
    cfg.to_json(path)
    return path


# ===========================================================================
# 命令行入口
# ===========================================================================
def _build_demo() -> Tuple[ReportConfig, ReportData]:
    """示例配置：数值留空/占位，实际使用时请替换为核实后的公开数据。"""
    cfg = ReportConfig(report_date='2026-09-07', data_date='2026-09-05',
                       output_date='2026-09-08', gen_time='09:00', fx_rate=6.72,
                       key_data='9月10日PPI、9月11日CPI', fomc_date='9月15-16日')
    data = ReportData(
        intl=[{'name': '伦敦金现货', 'price': None, 'chg': None, 'note': '待核实'},
              {'name': 'COMEX黄金期货(12月合约)', 'price': None, 'chg': None, 'note': '待核实'}],
        sge_day=[{'name': p, 'prev_close': None, 'close': None} for p in SGE_PRODUCTS],
        sge_night=[{'name': p, 'last': None, 'day_close': None} for p in SGE_PRODUCTS],
        brands=[{'brand': b} for b in BRAND_LIST],
        bullion=[{'name': n} for n in BULLION_LIST],
        risk=[{'level': lv, 'content': '待填（事件+影响程度+时间节点，20~50字）'}
              for lv in RISK_LEVELS],
        tech=[{'type': t} for t in TECH_LEVELS],
        institutions=[{'org': o} for o in INSTITUTION_LIST],
    )
    return cfg, data


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog='gold_price_report.py',
        description='金价每日速报生成器：输出下达给AI的完整Prompt、报告Markdown与A4 PDF')
    p.add_argument('--config', help='JSON 配置文件路径（ReportConfig 字段）')
    p.add_argument('--data', help='JSON 数据文件路径（ReportData 字段）')
    p.add_argument('--demo', action='store_true', help='使用内置示例配置试跑')
    p.add_argument('--report-date', dest='report_date', help='报告日期 YYYY-MM-DD')
    p.add_argument('--data-date', dest='data_date', help='数据截止日（上一SGE交易日）')
    p.add_argument('--output-date', dest='output_date', help='下一交易日（夜盘归属日）')
    p.add_argument('--time', dest='gen_time', help='报告生成时间 HH:MM')
    p.add_argument('--dept', dest='dept', help='出具部门名称')
    p.add_argument('--fx', dest='fx_rate', type=float, help='在岸人民币汇率')
    p.add_argument('--key-data', dest='key_data', help='下周关键数据日期')
    p.add_argument('--fomc', dest='fomc_date', help='FOMC 会议日期')
    p.add_argument('--image', dest='trend_image', help='趋势长图路径（可选，插入PDF）')
    p.add_argument('--prompt', dest='prompt_out', help='Prompt 输出 txt 路径')
    p.add_argument('--md', dest='md_out', help='Markdown 输出路径')
    p.add_argument('--pdf', dest='pdf_out', help='PDF 输出路径（需 reportlab）')
    p.add_argument('--example-config', help='仅导出 JSON 配置样例到指定路径后退出')
    p.add_argument('--print', action='store_true', help='把 Prompt 打印到标准输出')
    p.add_argument('--check', action='store_true', help='执行质检清单并打印结果')
    p.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = p.parse_args(argv)

    if args.example_config:
        print('示例配置已写入：' + write_config_example(args.example_config))
        return 0

    if args.config:
        cfg = ReportConfig.from_json(args.config)
    else:
        base = _build_demo() if args.demo else (ReportConfig(), None)
        cfg = base[0]
        for name in ('report_date', 'data_date', 'output_date', 'gen_time', 'dept',
                     'fx_rate', 'key_data', 'fomc_date', 'trend_image'):
            val = getattr(args, name, None)
            if val is not None:
                setattr(cfg, name, val)
        if args.demo:
            cfg.__post_init__()
    if args.data:
        data = ReportData.from_json(args.data)
    elif args.demo:
        data = _build_demo()[1]
    else:
        data = None
    if args.trend_image:
        cfg.trend_image = args.trend_image

    prompt = build_prompt(cfg, data)
    markdown = build_markdown(cfg, data)

    if args.print or not any([args.prompt_out, args.md_out, args.pdf_out]):
        print(prompt)

    if args.prompt_out:
        with open(args.prompt_out, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f'Prompt 已写入：{os.path.abspath(args.prompt_out)}')
    if args.md_out:
        with open(args.md_out, 'w', encoding='utf-8') as f:
            f.write(markdown)
        print(f'Markdown 已写入：{os.path.abspath(args.md_out)}')
    if args.pdf_out:
        try:
            print('PDF 已写入：' + os.path.abspath(
                render_pdf(cfg, data, args.pdf_out)))
        except RuntimeError as exc:
            print(f'PDF 未生成：{exc}；Markdown 版本仍可用', file=sys.stderr)

    if args.check:
        print('\n=== 质量检查清单（自动可判定项）===')
        for ok, msg in quality_check(cfg, data or ReportData()):
            print(('[通过] ' if ok else '[待补] ') + msg)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
