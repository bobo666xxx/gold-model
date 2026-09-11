# 金价每日速报 · Streamlit 部署版

在网页端一键生成《金价每日速报》PDF 报告、金价趋势长图、黄金原料采购操作小结。
部署地址：https://gold-model-bmdtpsvwkxszf25wzhqpk9.streamlit.app/

## 为什么这版能在 Streamlit Cloud 跑通
- 前几轮反复失败的根因：Streamlit Cloud 服务器在海外，国内财经接口（akshare、miaoxi 等）
  对该环境直接拒绝，所以无论换哪个国内接口都会"取不到数据/无法解析域名"。
- 本版策略：
  1) 国际金价、美元兑人民币 —— 实时从海外可直连、无需密钥的接口拉取：
     金价 `api.gold-api.com/price/XAU`（失败自动回落新浪 hf_XAU）；汇率 `open.er-api.com`。
  2) 国内 SGE 行情、品牌金饰、投资金条、机构观点等 —— 放在 `data_config.py`，
     由你在部署端按公开渠道（上金所官网/金投网/汇通财经/金价查询网等）核对填写。
  3) PDF 中文用 reportlab 内置中文字体 `STSong-Light`，云端无需安装任何字体文件。

## 文件说明
- `streamlit_app.py`  主程序（页面 UI + PDF/长图/小结生成器）。
- `data_config.py`   国内数据配置（你日常只需编辑这一个文件）。
- `requirements.txt` 依赖清单（已含 reportlab、matplotlib，用于云端出 PDF/图）。
- `README.md`        本说明。

## 上传与部署（最短路径）
1. GitHub 仓库 `bobo666xxx/gold-model` → Add file → Upload files，把这 4 个文件一起拖入，
   同名提示覆盖时确认覆盖 → Commit changes。
2. 打开应用页 → 右上角 Manage app → 先 Clear cache，再 Reboot。
3. 状态变 Running 后刷新页面，点"重新生成"即可。

## 每天怎么用
1. 打开 `data_config.py`，把 SGE 日盘/夜盘收盘、品牌金饰价、投资金条价、机构目标价等
   填成当天公开数据（无法核实的保留"待核实"，切勿编造）。
2. 提交后 Reboot（或页面点"重新生成"），下载 PDF / 长图 / 小结。
3. 核心国际金价、汇率、国内折算价由程序实时获取，无需手填。

## 数据与口径
- 页面/PDF 中的人民币价 = 国际金价 × 实时汇率 ÷ 31.1035（交易所大盘参考价），
  低于周大福等金店零售价属正常（后者含加工费与品牌溢价）。
- SGE 延时行情"收盘价"未结算时显示"待结算"，以官网 15:30 历史行情为准。

## 不出数时排查顺序
1. Manage app → Logs 看具体报错。
2. Clear cache 后刷新。
3. 确认 requirements.txt 未被删（需含 reportlab、matplotlib）。
4. 若接口临时波动，稍后再点"重新生成"，程序会自动在多个数据源间回退。

风险提示：以上内容仅供参考，投资有风险，入市需谨慎。
