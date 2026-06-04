# 项目结构概览

本文档说明 `BETA_MMT_V1` 当前真实目录结构、核心模块、运行脚本、文档和主要输出。项目当前主线是 **Barra CNE6 风格因子择时策略**，并已扩展到 **年度 Alpha 精选版**：先用 Barra 风格择时构造 `Barra Top500` 前置池，再用年度滚动 Alpha 因子池筛选 `Alpha Top50`。

当前报告主线为：

```text
docs/CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.*
```

## 顶层目录

```text
beta_mmt_v1/
|-- src/                    # 核心源码
|-- scripts/                # 可直接运行的脚本入口, 按 backtest/analysis/optimize/report 分组
|-- docs/                   # 项目文档、研究留痕和最终策略报告
|-- output/                 # 回测、缓存、分析输出和报告图片
|-- prompt_doc/             # 历史提示词和参考资料
|-- README.md               # 项目总览和常用命令
|-- PROJECT_STRUCTURE.md    # 当前文件
|-- requirements.txt        # Python 依赖
`-- setup.py                # 包配置
```

## 源码目录

```text
src/
|-- models/
|   |-- barra_cne5.py
|   `-- barra_cne6.py
|-- strategies/
|   |-- active_factor_screener.py
|   |-- factor_timing_strategy_v3.py
|   `-- yearly_factor_candidate_pool.py
|-- analysis/
|   |-- factor_weight_experiment.py
|   |-- residual_attribution.py
|   |-- style_factor_attribution.py
|   `-- transaction_cost_stress.py
|-- optimize/
|   |-- core_parameter_stability.py
|   |-- execution_capacity_experiment.py
|   |-- execution_turnover_revaluation.py
|   |-- execution_turnover_walk_forward.py
|   `-- turnover_control_experiment.py
`-- utils/
    |-- db.py
    |-- benchmark.py
    `-- trade_recorder.py
```

### `src/models/`

| 文件 | 作用 |
|---|---|
| `barra_cne6.py` | 当前主线 Barra CNE6 风格因子模型，生成因子暴露、因子收益、累计收益和价格缓存 |
| `barra_cne5.py` | CNE5 历史模型实现，当前主要作为保留参考 |

### `src/strategies/`

| 文件 | 作用 |
|---|---|
| `factor_timing_strategy_v3.py` | 主策略：风格择时信号、理想风格向量、相似度选股、周频回测、换手控制、绩效图表和交易记录 |
| `yearly_factor_candidate_pool.py` | 年度 Alpha 候选池构建与读取，用于年度滚动精选 Alpha 因子后再筛股票 |
| `active_factor_screener.py` | 主动因子二次筛选模块，当前不是最终报告默认方案 |

### `src/analysis/`

| 文件 | 作用 |
|---|---|
| `style_factor_attribution.py` | 风格收益归因、分时段归因、择时有效性和持仓暴露质量分析 |
| `transaction_cost_stress.py` | 单/双边成本压力、首期建仓、ADV 冲击成本和真实成本口径评估 |
| `factor_weight_experiment.py` | 因子剔除/降权实验 |
| `residual_attribution.py` | residual 归因和共同项拆解 |

### `src/optimize/`

| 文件 | 作用 |
|---|---|
| `turnover_control_experiment.py` | 换手控制参数网格实验 |
| `execution_capacity_experiment.py` | 资金规模、ADV 参与率、涨跌停近似约束下的成交可实现性与容量实验 |
| `execution_turnover_revaluation.py` | 将换手参数与执行成本、成交约束合并重估 |
| `execution_turnover_walk_forward.py` | 年度 walk-forward 动态选参验证 |
| `core_parameter_stability.py` | 核心择时参数稳定性、邻域参数和 walk-forward 稳健性检验 |

### `src/utils/`

| 文件 | 作用 |
|---|---|
| `db.py` | 统一从环境变量读取数据库 URL 并创建 SQLAlchemy engine，避免源码泄露账号信息 |
| `benchmark.py` | 读取指数数据，计算周频基准收益与相对收益 |
| `trade_recorder.py` | 记录调仓、买卖和持仓变化，导出交易记录 |

## 脚本目录

```text
scripts/
|-- backtest/
|   |-- regenerate_and_run.py
|   |-- run_factor_timing_cne5.py
|   |-- run_factor_timing_v3.py
|   |-- run_factor_timing_with_yearly_pool.py
|   `-- run_from_scratch.py
|-- analysis/
|   |-- run_residual_attribution_cne6.py
|   |-- run_style_factor_attribution_cne6.py
|   |-- run_style_factor_attribution_regime_cne6.py
|   |-- run_style_factor_attribution_summary_cne6.py
|   |-- run_style_holding_exposure_quality_cne6.py
|   |-- run_style_timing_effectiveness_cne6.py
|   `-- run_transaction_cost_stress_cne6.py
|-- optimize/
|   |-- run_core_parameter_stability_cne6.py
|   |-- run_execution_capacity_experiment_cne6.py
|   |-- run_execution_turnover_revaluation_cne6.py
|   |-- run_execution_turnover_walk_forward_cne6.py
|   |-- run_factor_timing_turnover_control_cne6.py
|   |-- run_factor_weight_experiment_cne6.py
|   `-- run_turnover_control_experiment_cne6.py
`-- report/
    |-- build_2026_case_analysis.py
    |-- build_alpha_constraint_curve.py
    |-- build_alpha_nav_comparison_figure.py
    |-- build_alpha_selected_report_updates.py
    |-- build_final_report_figures.py
    |-- render_strategy_report_pdf.py
    `-- render_strategy_report_sample_style.py
```

### 回测脚本

| 脚本 | 说明 |
|---|---|
| `scripts/backtest/run_factor_timing_v3.py` | 原始 CNE6 风格择时主回测入口，优先使用已有缓存 |
| `scripts/backtest/run_factor_timing_with_yearly_pool.py` | 年度 Alpha 池版本回测入口，可运行年度因子池或 Alpha TopN 组合 |
| `scripts/backtest/regenerate_and_run.py` | 重新生成 Barra CNE6 数据后运行主策略，会覆盖基础缓存和主回测结果 |
| `scripts/backtest/run_factor_timing_cne5.py` | CNE5 历史回测脚本 |
| `scripts/backtest/run_from_scratch.py` | 历史完整流程入口，使用当前项目根目录下的 `output/cne6/` |

### 分析脚本

| 脚本 | 说明 |
|---|---|
| `scripts/analysis/run_style_factor_attribution_cne6.py` | 风格归因分析整合入口 |
| `scripts/analysis/run_style_factor_attribution_summary_cne6.py` | 全样本风格因子收益归因 |
| `scripts/analysis/run_style_factor_attribution_regime_cne6.py` | 分时段风格因子收益归因，时段设置写在脚本内 |
| `scripts/analysis/run_style_timing_effectiveness_cne6.py` | 风格择时有效性分析 |
| `scripts/analysis/run_style_holding_exposure_quality_cne6.py` | 持仓内部风格暴露质量分析 |
| `scripts/analysis/run_transaction_cost_stress_cne6.py` | 交易成本压力、双边建仓和 ADV 冲击成本评估 |
| `scripts/analysis/run_residual_attribution_cne6.py` | residual 归因 |

### 优化脚本

| 脚本 | 说明 |
|---|---|
| `scripts/optimize/run_factor_timing_turnover_control_cne6.py` | 单组换手控制版 CNE6 回测 |
| `scripts/optimize/run_turnover_control_experiment_cne6.py` | 换手控制参数网格实验 |
| `scripts/optimize/run_factor_weight_experiment_cne6.py` | 因子剔除/降权实验 |
| `scripts/optimize/run_execution_capacity_experiment_cne6.py` | baseline 与换手控制组合在不同资金规模和 ADV 上限下的成交容量实验 |
| `scripts/optimize/run_execution_turnover_revaluation_cne6.py` | 多组换手参数在成本和成交约束下的重估 |
| `scripts/optimize/run_execution_turnover_walk_forward_cne6.py` | 年度 walk-forward 动态换手选参验证 |
| `scripts/optimize/run_core_parameter_stability_cne6.py` | 核心参数稳定性与邻域组合检验 |

### 报告脚本

| 脚本 | 说明 |
|---|---|
| `scripts/report/build_final_report_figures.py` | 读取原始风格择时优化和分析输出，生成最终报告专用图表 |
| `scripts/report/build_2026_case_analysis.py` | 基于 2026 数据生成补充案例曲线、指标和明细 |
| `scripts/report/build_alpha_selected_report_updates.py` | 生成 Alpha 精选版实验输出、报告图表和 2026 案例 |
| `scripts/report/build_alpha_nav_comparison_figure.py` | 生成图 5.1：原始策略与 Alpha 版累计净值、基准和回撤对比 |
| `scripts/report/build_alpha_constraint_curve.py` | 生成 6.3：baseline 成本与成交约束前后曲线，并把指标表嵌入图中 |
| `scripts/report/render_strategy_report_sample_style.py` | 将最终主文档 Markdown 渲染为 HTML/PDF |
| `scripts/report/render_strategy_report_pdf.py` | 将研究留痕版 Markdown 渲染为 HTML/PDF |

## 文档目录

```text
docs/
|-- CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.md
|-- CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.html
|-- CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.pdf
|-- BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.md
|-- BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.html
|-- BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.pdf
|-- BETA_MMT_V1_CNE6风格择时策略_优化实验记录.md
|-- 原项目完整复现文档.md
`-- 原项目详细说明文档.md
```

| 文件 | 说明 |
|---|---|
| `CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.*` | 当前主线最终报告，覆盖原始策略、Alpha 精选、成本成交约束、核心参数稳定性和定稿选择 |
| `BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.*` | 研究过程留痕版报告 |
| `BETA_MMT_V1_CNE6风格择时策略_优化实验记录.md` | 优化实验过程记录 |
| `原项目完整复现文档.md`、`原项目详细说明文档.md` | 原始项目复现与说明材料 |

## 输出目录

`output/` 保存大体量缓存、回测结果和分析图表。当前 `.gitignore` 只对部分超大生成文件做了单独忽略，不代表整个 `output/` 都不会进入版本管理。

```text
output/
|-- README.md
|-- report_html_preview.png
`-- cne6/
    |-- data/
    |-- images/
    |   |-- backtest/
    |   |-- analysis/
    |   |-- optimize/
    |   `-- report/
    `-- logs/
```

### `output/cne6/data/`

| 类型 | 文件示例 |
|---|---|
| Barra CNE6 基础缓存 | `factor_exposure_cne6.csv`、`price_data_cne6.csv`、`factor_returns_cne6.csv`、`cumulative_returns_cne6.csv`、`factor_summary_cne6.xlsx`、`index_eod.csv` |
| 原始主策略结果 | `portfolio_returns_l20_s5_b2_e1_n100.csv`、`optimal_vectors_l20_s5_b2_e1_n100.csv`、`annual_returns_l20_s5_b2_e1_n100.csv`、`monthly_win_rate_l20_s5_b2_e1_n100.csv`、`benchmark_relative_l20_s5_b2_e1_n100.csv`、`交易记录_l20_s5_b2_e1_n100.xlsx` |
| 年度 Alpha 精选结果 | `portfolio_returns_l20_s5_b2_e1_n500_alpha50.csv`、`annual_returns_l20_s5_b2_e1_n500_alpha50.csv`、`monthly_win_rate_l20_s5_b2_e1_n500_alpha50.csv`、`benchmark_relative_l20_s5_b2_e1_n500_alpha50.csv`、`barra_alpha_grid_comparison.csv` |
| 年度 Alpha 池缓存 | `yearly_factor_pool/`、`yearly_factor_pool_summary_*` |
| 成本压力 | `transaction_cost_stress_*`、`transaction_cost_realistic_*` |
| 风格与 residual 归因 | `style_factor_attribution_*`、`style_timing_effectiveness_*`、`style_holding_exposure_quality_*`、`residual_attribution_*` |
| 换手与因子实验 | `turnover_control_experiment_*`、`factor_weight_experiment_*` |
| 成交容量与重估 | `execution_capacity_*`、`execution_turnover_revaluation_*`、`execution_turnover_walk_forward_*` |
| 核心参数稳定性 | `core_parameter_stability_*` |
| 2026 案例 | `case_2026_factor_returns_*`、`case_2026_portfolio_returns_*`、`case_2026_execution_detail_*`、`case_2026_summary_*` |

### `output/cne6/images/`

| 子目录 | 内容 |
|---|---|
| `backtest/` | 主回测净值图、CNE6 风格因子累计收益图 |
| `analysis/` | 风格归因、分时段归因、择时有效性、持仓暴露质量、成本压力测试、residual 归因 |
| `optimize/` | 因子剔除/降权、换手控制、成交容量、walk-forward 和核心参数稳定性图 |
| `report/` | 最终主报告专用图片，包括净值对比、成本成交约束对比、容量图、核心参数稳定性图和 2026 案例图 |

## 推荐运行顺序

如果已有 `output/cne6/data/` 基础缓存，推荐顺序为：

```bash
python scripts/backtest/run_factor_timing_v3.py
python scripts/backtest/run_factor_timing_with_yearly_pool.py
python scripts/analysis/run_transaction_cost_stress_cne6.py
python scripts/optimize/run_turnover_control_experiment_cne6.py
python scripts/optimize/run_execution_capacity_experiment_cne6.py
python scripts/optimize/run_execution_turnover_revaluation_cne6.py
python scripts/optimize/run_execution_turnover_walk_forward_cne6.py
python scripts/optimize/run_core_parameter_stability_cne6.py
python scripts/analysis/run_style_factor_attribution_summary_cne6.py
python scripts/analysis/run_style_factor_attribution_regime_cne6.py
python scripts/analysis/run_style_timing_effectiveness_cne6.py
python scripts/analysis/run_style_holding_exposure_quality_cne6.py
python scripts/analysis/run_residual_attribution_cne6.py
python scripts/report/build_alpha_selected_report_updates.py
python scripts/report/build_alpha_nav_comparison_figure.py
python scripts/report/build_alpha_constraint_curve.py
python scripts/report/render_strategy_report_sample_style.py
```

研究留痕版报告可单独运行：

```bash
python scripts/report/render_strategy_report_pdf.py
```

## 当前状态备注

- CNE6 是当前主线，CNE5 保留为历史参考。
- 原始策略默认结果后缀为 `l20_s5_b2_e1_n100`。
- Alpha 精选主观察结果后缀为 `l20_s5_b2_e1_n500_alpha50`。
- 当前主报告引入年度 Alpha 因子筛选，Alpha 池以量价和日内微观结构因子为主，年度滚动更新。
- 成本与成交约束口径已从旧版双边成本主线调整为买入单边 `10bp` 固定成本、首期建仓不计固定成本、ADV 平方根冲击成本和成交上限约束。
- 主样本报告覆盖 `2020-02-17 ~ 2025-12-22`，并补充 2026 年案例分析。
- 数据库连接从环境变量读取，真实 MySQL 账号信息不进入版本库。
- 多数脚本会覆盖同名输出文件，运行前应确认当前输出是否需要保留。

**最后更新：** 2026-06-03
