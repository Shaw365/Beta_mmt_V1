# 项目结构概览

本文档用于说明 `BETA_MMT_V1` 当前真实的目录结构、核心模块、运行脚本和主要输出。项目当前主线是 **Barra CNE6 风格因子择时策略**。

## 顶层目录

```text
beta_mmt_v1/
├── src/                    # 核心源码
├── scripts/                # 可直接运行的脚本入口
├── docs/                   # 项目文档与策略报告
├── output/                 # 回测、缓存和分析输出，已被 .gitignore 忽略
├── prompt_doc/             # 历史参考资料
├── README.md               # 项目总览
├── PROJECT_STRUCTURE.md    # 当前文件
├── requirements.txt        # Python 依赖
└── setup.py                # 包配置
```

## 源码目录

```text
src/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── barra_cne5.py
│   └── barra_cne6.py
├── strategies/
│   ├── __init__.py
│   ├── active_factor_screener.py
│   └── factor_timing_strategy_v3.py
├── analysis/
│   ├── __init__.py
│   ├── style_factor_attribution.py
│   ├── transaction_cost_stress.py
│   ├── factor_weight_experiment.py
│   └── residual_attribution.py
└── utils/
    ├── __init__.py
    ├── benchmark.py
    └── trade_recorder.py
```

### `src/models/`

| 文件 | 作用 |
|---|---|
| `barra_cne6.py` | 当前主线 Barra CNE6 风格因子模型，生成因子暴露、因子收益、累计收益和基础缓存 |
| `barra_cne5.py` | CNE5 历史模型实现，当前主要作为保留参考 |

`barra_cne6.py` 当前覆盖 25 个 CNE6 风格因子：

```text
SIZE, MIDCAP,
BETA, RESVOL, HISTVOL,
MOMENTUM, RESMOM,
BTOP, EYIELD, CFP, SP, LP,
EGRO, SGRO,
MLEV, BLEV,
LIQUIDITY, STOM, STOQ,
ROE, ROA,
CAPX, AGRO,
TOPSI, SEASON
```

### `src/strategies/`

| 文件 | 作用 |
|---|---|
| `factor_timing_strategy_v3.py` | 当前主策略：风格择时信号、理想风格向量、相似度选股、周频回测、绩效图表和交易记录 |
| `active_factor_screener.py` | 主动因子二次筛选模块，当前不是主回测默认入口 |

当前主策略逻辑为：

```text
风格因子累计收益
→ 通道位置/分档信号
→ 理想风格向量
→ 股票 CNE6 暴露与理想向量的余弦相似度
→ 选择 Top N 股票
→ 周频调仓回测
```

### `src/analysis/`

| 文件 | 作用 |
|---|---|
| `style_factor_attribution.py` | 风格收益归因、分时段归因、择时有效性、持仓暴露质量分析 |
| `transaction_cost_stress.py` | 交易成本压力测试 |
| `factor_weight_experiment.py` | 因子剔除/降权实验 |
| `residual_attribution.py` | residual 归因 |

当前分析模块默认读取的主策略后缀为：

```text
l20_s5_b2_e1_n100
```

### `src/utils/`

| 文件 | 作用 |
|---|---|
| `benchmark.py` | 读取指数数据，计算周频基准收益与相对收益 |
| `trade_recorder.py` | 记录调仓、买卖和持仓变化，导出交易记录 |

## 脚本目录

```text
scripts/
├── run_factor_timing_v3.py
├── run_factor_timing_cne5.py
├── run_from_scratch.py
├── regenerate_and_run.py
├── run_style_factor_attribution_cne6.py
├── run_style_factor_attribution_summary_cne6.py
├── run_style_factor_attribution_regime_cne6.py
├── run_style_timing_effectiveness_cne6.py
├── run_style_holding_exposure_quality_cne6.py
├── run_transaction_cost_stress_cne6.py
├── run_factor_weight_experiment_cne6.py
├── run_residual_attribution_cne6.py
└── render_strategy_report_pdf.py
```

### 主回测脚本

| 脚本 | 说明 |
|---|---|
| `run_factor_timing_v3.py` | 当前推荐的 CNE6 主回测入口，优先使用已有缓存 |
| `regenerate_and_run.py` | 重新生成 Barra CNE6 数据后运行主策略 |
| `run_from_scratch.py` | 历史完整流程入口，目前仍有部分旧绝对路径，使用前建议检查 |
| `run_factor_timing_cne5.py` | CNE5 历史回测脚本 |

### 风格归因与择时诊断脚本

| 脚本 | 说明 |
|---|---|
| `run_style_factor_attribution_summary_cne6.py` | 全样本风格因子收益归因 |
| `run_style_factor_attribution_regime_cne6.py` | 分时段风格因子收益归因 |
| `run_style_timing_effectiveness_cne6.py` | 风格择时有效性分析 |
| `run_style_holding_exposure_quality_cne6.py` | 持仓内部风格暴露质量分析 |
| `run_style_factor_attribution_cne6.py` | 归因分析的历史整合入口/兼容入口 |

`run_style_factor_attribution_regime_cne6.py` 当前分时段设置为：

| regime | 起始日 | 结束日 |
|---|---:|---:|
| `steady_2020_to_2024_pre_jump` | 2020-02-17 | 2024-09-18 |
| `jump_2024_q4` | 2024-09-23 | 2024-12-09 |
| `jump_2025_mid` | 2025-04-07 | 2025-09-29 |

### 策略稳健性和 residual 分析脚本

| 脚本 | 说明 |
|---|---|
| `run_transaction_cost_stress_cne6.py` | 单边交易成本压力测试 |
| `run_factor_weight_experiment_cne6.py` | 因子剔除/降权实验 |
| `run_residual_attribution_cne6.py` | residual 归因 |

### 报告脚本

| 脚本 | 说明 |
|---|---|
| `render_strategy_report_pdf.py` | 将 Markdown 策略报告渲染为图文版 HTML/PDF |

该脚本读取：

```text
docs/BETA_MMT_V1_CNE6风格择时策略报告.md
```

输出：

```text
docs/BETA_MMT_V1_CNE6风格择时策略报告_图文版.html
docs/BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf
docs/BETA_MMT_V1_CNE6风格择时策略报告.pdf
```

## 文档目录

```text
docs/
├── BETA_MMT_V1_CNE6风格择时策略报告.md
├── BETA_MMT_V1_CNE6风格择时策略报告.pdf
├── BETA_MMT_V1_CNE6风格择时策略报告_图文版.html
├── BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf
├── 项目完整复现文档.md
└── 项目详细说明文档.md
```

| 文件 | 说明 |
|---|---|
| `BETA_MMT_V1_CNE6风格择时策略报告.md` | 可编辑的策略报告源文件 |
| `BETA_MMT_V1_CNE6风格择时策略报告.pdf` | 当前标准 PDF 报告 |
| `BETA_MMT_V1_CNE6风格择时策略报告_图文版.html` | 图文版 HTML 报告 |
| `BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf` | 图文版 PDF 报告 |
| `项目完整复现文档.md` | 历史复现说明 |
| `项目详细说明文档.md` | 历史详细说明 |

## 输出目录

`output/` 已经在 `.gitignore` 中忽略，用于保存大体量缓存、回测结果和分析图表。

当前主要输出集中在：

```text
output/cne6/
├── data/
├── images/
└── factor_timing_l20_s5_b2_e1_n100.png
```

### `output/cne6/data/`

#### Barra CNE6 基础缓存

| 文件 | 说明 |
|---|---|
| `factor_exposure_cne6.csv` | 股票-日期维度的 CNE6 风格因子暴露 |
| `price_data_cne6.csv` | 回测使用的股票价格数据 |
| `factor_returns_cne6.csv` | CNE6 风格因子收益 |
| `cumulative_returns_cne6.csv` | CNE6 风格因子累计收益 |
| `factor_summary_cne6.xlsx` | 因子汇总表 |
| `index_eod.csv` | 指数行情缓存 |

#### 主策略输出

| 文件 | 说明 |
|---|---|
| `portfolio_returns_l20_s5_b2_e1_n100.csv` | 每期组合收益、持仓、换手等 |
| `optimal_vectors_l20_s5_b2_e1_n100.csv` | 每期理想风格向量 |
| `annual_returns_l20_s5_b2_e1_n100.csv` | 年度收益 |
| `monthly_win_rate_l20_s5_b2_e1_n100.csv` | 月度胜率 |
| `benchmark_relative_l20_s5_b2_e1_n100.csv` | 相对基准表现 |
| `交易记录_l20_s5_b2_e1_n100.xlsx` | 调仓交易记录 |

#### 分析输出

| 前缀 | 说明 |
|---|---|
| `style_factor_attribution_*` | 风格收益归因明细、汇总和分时段结果 |
| `style_timing_effectiveness_*` | 风格择时有效性明细与汇总 |
| `style_holding_exposure_quality_*` | 持仓内部暴露质量明细与汇总 |
| `transaction_cost_stress_*` | 交易成本压力测试明细、汇总和年度结果 |
| `factor_weight_experiment_*` | 因子剔除/降权实验收益、汇总、年度结果和权重表 |
| `residual_attribution_*` | residual 逐期、逐股、分组和组件汇总结果 |

### `output/cne6/images/`

| 文件 | 说明 |
|---|---|
| `cumulative_returns_cne6.png` | CNE6 风格因子累计收益图 |
| `style_factor_attribution_summary_l20_s5_b2_e1_n100.png` | 全样本风格收益归因图 |
| `style_factor_attribution_regime_summary_l20_s5_b2_e1_n100.png` | 分时段风格收益归因图 |
| `style_timing_effectiveness_table_l20_s5_b2_e1_n100.png` | 风格择时有效性表 |
| `style_holding_exposure_quality_table_l20_s5_b2_e1_n100.png` | 持仓内部暴露质量表 |
| `transaction_cost_stress_l20_s5_b2_e1_n100.png` | 交易成本压力测试图 |
| `factor_weight_experiment_l20_s5_b2_e1_n100.png` | 因子剔除/降权实验图 |
| `residual_attribution_l20_s5_b2_e1_n100.png` | residual 归因图 |

## 快速运行顺序

如果已有 `output/cne6/data/` 缓存，推荐顺序为：

```bash
python scripts/run_factor_timing_v3.py
python scripts/run_style_factor_attribution_summary_cne6.py
python scripts/run_style_factor_attribution_regime_cne6.py
python scripts/run_style_timing_effectiveness_cne6.py
python scripts/run_style_holding_exposure_quality_cne6.py
python scripts/run_transaction_cost_stress_cne6.py
python scripts/run_factor_weight_experiment_cne6.py
python scripts/run_residual_attribution_cne6.py
python scripts/render_strategy_report_pdf.py
```

## 当前状态备注

- CNE6 是当前主线；CNE5 保留为历史参考。
- 分析模块默认绑定 `l20_s5_b2_e1_n100` 这一组主策略输出。
- `output/` 中包含大文件，不应纳入版本管理。
- 报告 PDF 由 `render_strategy_report_pdf.py` 生成，依赖本机 Chrome 或 Edge。
- `run_from_scratch.py` 中仍有旧项目绝对路径，后续可单独清理。

**最后更新：** 2026-04-30
