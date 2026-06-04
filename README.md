# BETA_MMT_V1: CNE6 Style Timing And Annual Alpha Selection

本项目围绕 **Barra CNE6 风格因子择时选股策略** 展开。当前研究主线已经从原始 `Barra Top100` 风格择时组合，扩展到 `Barra Top500 -> Alpha Top50` 年度 Alpha 精选组合，并配套完成了成本、成交约束、换手控制、容量、归因和报告渲染流程。

当前主观察版本：

```text
风格择时参数: L20 / S5 / B2 / E1
原始策略: Barra Top100
Alpha精选版: Barra Top500 -> Alpha Top50
Alpha池来源: yearly_rankic5d_20260526_090335 年度滚动筛选结果
主执行口径: 买入单边 10bp 固定成本 + ADV 平方根冲击成本 + 成交上限约束
主观察资金: 1000万 / 3000万 / 1亿, 重点观察 10% ADV
主样本区间: 2020-02-17 ~ 2025-12-22
补充案例: 2026 年样本外案例
```

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括 `pandas`、`numpy`、`sqlalchemy`、`pymysql`、`matplotlib`、`seaborn`、`scipy`、`statsmodels`、`openpyxl`。

部分脚本会访问 MySQL 数据库。数据库连接统一从环境变量读取，真实账号信息不应写入源码。可参考 `.env.example`：

```bash
BETA_MMT_FINANCE_DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/stock_finance
BETA_MMT_MARKET_DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/stock_market
BETA_MMT_BASIC_DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/stock_basic
BETA_MMT_INDEX_DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/index_market
```

如果只基于已有 `output/cne6/data/` 缓存运行，不一定需要重新访问数据库。

## 快速入口

原始 CNE6 风格择时回测：

```bash
python scripts/backtest/run_factor_timing_v3.py
```

年度 Alpha 池版本回测：

```bash
python scripts/backtest/run_factor_timing_with_yearly_pool.py
```

Alpha 精选版第 6-8 章实验和图表更新：

```bash
python scripts/report/build_alpha_selected_report_updates.py
```

报告专项图更新：

```bash
python scripts/report/build_alpha_nav_comparison_figure.py
python scripts/report/build_alpha_constraint_curve.py
```

最终主报告渲染：

```bash
python scripts/report/render_strategy_report_sample_style.py
```

## 主要报告文件

```text
docs/CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.md
docs/CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.html
docs/CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.pdf

docs/BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.md
docs/BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.html
docs/BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.pdf
```

旧版 `BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.*` 已不再作为当前主线报告使用，当前主线报告是 `CNE6风格择时与年度Alpha精选策略研究报告_最终主文档.*`。

## 当前项目结构

```text
beta_mmt_v1/
|-- src/                    # 核心源码
|   |-- models/              # Barra CNE5/CNE6 因子模型
|   |-- strategies/          # 风格择时、相似度选股、年度 Alpha 池
|   |-- analysis/            # 归因、成本压力、因子权重实验
|   |-- optimize/            # 换手控制、成交约束、容量和参数稳定性
|   `-- utils/               # 数据库、指数基准、交易记录工具
|-- scripts/                # 可直接运行的脚本入口
|   |-- backtest/
|   |-- analysis/
|   |-- optimize/
|   `-- report/
|-- docs/                   # 项目文档与策略报告
|-- output/                 # 缓存、回测、分析图表和报告图片
|-- prompt_doc/             # 历史参考材料
|-- PROJECT_STRUCTURE.md    # 更详细的目录说明
|-- requirements.txt
`-- setup.py
```

更详细的文件说明见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

## 常用脚本

### 回测

```bash
python scripts/backtest/run_factor_timing_v3.py
python scripts/backtest/run_factor_timing_with_yearly_pool.py
python scripts/backtest/regenerate_and_run.py
python scripts/backtest/run_factor_timing_cne5.py
python scripts/backtest/run_from_scratch.py
```

`run_factor_timing_v3.py` 是原始 CNE6 风格择时主回测入口。`run_factor_timing_with_yearly_pool.py` 用于基于年度 Alpha 候选池运行组合版本。`regenerate_and_run.py` 会重新生成 Barra CNE6 数据并覆盖相关缓存，运行前应确认数据库可访问。

### 分析

```bash
python scripts/analysis/run_style_factor_attribution_summary_cne6.py
python scripts/analysis/run_style_factor_attribution_regime_cne6.py
python scripts/analysis/run_style_timing_effectiveness_cne6.py
python scripts/analysis/run_style_holding_exposure_quality_cne6.py
python scripts/analysis/run_transaction_cost_stress_cne6.py
python scripts/analysis/run_residual_attribution_cne6.py
```

这些脚本主要消费 `output/cne6/data/portfolio_returns_*`、`factor_returns_cne6.csv`、`price_data_cne6.csv` 等缓存，并输出风格归因、择时有效性、持仓暴露质量、成本压力和 residual 归因结果。

### 优化与执行约束

```bash
python scripts/optimize/run_turnover_control_experiment_cne6.py
python scripts/optimize/run_factor_weight_experiment_cne6.py
python scripts/optimize/run_execution_capacity_experiment_cne6.py
python scripts/optimize/run_execution_turnover_revaluation_cne6.py
python scripts/optimize/run_execution_turnover_walk_forward_cne6.py
python scripts/optimize/run_core_parameter_stability_cne6.py
```

这些脚本用于评估换手参数、成交完成率、ADV 参与率、资金规模、walk-forward 动态选参和核心参数稳定性。部分输出文件体量较大。

### 报告

```bash
python scripts/report/build_final_report_figures.py
python scripts/report/build_2026_case_analysis.py
python scripts/report/build_alpha_selected_report_updates.py
python scripts/report/build_alpha_nav_comparison_figure.py
python scripts/report/build_alpha_constraint_curve.py
python scripts/report/render_strategy_report_sample_style.py
python scripts/report/render_strategy_report_pdf.py
```

- `build_final_report_figures.py`: 生成原始风格择时报告专用图表。
- `build_2026_case_analysis.py`: 生成 2026 案例分析数据和图表。
- `build_alpha_selected_report_updates.py`: 生成 Alpha 精选版第 6-8 章实验结果、图表和 2026 案例。
- `build_alpha_nav_comparison_figure.py`: 生成图 5.1 的原始策略与 Alpha 版净值/回撤对比。
- `build_alpha_constraint_curve.py`: 生成 6.3 中成本与成交约束前后净值对比图。
- `render_strategy_report_sample_style.py`: 渲染最终主文档 HTML/PDF。
- `render_strategy_report_pdf.py`: 渲染研究留痕版 HTML/PDF。

## 核心输出

### `output/cne6/data/`

主要包含：

- 基础缓存：`factor_exposure_cne6.csv`、`price_data_cne6.csv`、`factor_returns_cne6.csv`、`cumulative_returns_cne6.csv`、`index_eod.csv`
- 原始主回测：`portfolio_returns_l20_s5_b2_e1_n100.csv`、`optimal_vectors_l20_s5_b2_e1_n100.csv`、`benchmark_relative_l20_s5_b2_e1_n100.csv`
- Alpha 精选回测：`portfolio_returns_l20_s5_b2_e1_n500_alpha50.csv`、`barra_alpha_grid_comparison.csv`
- 年度 Alpha 池：`yearly_factor_pool/`、`yearly_factor_pool_summary_*`
- 成本与成交：`transaction_cost_*`、`execution_capacity_*`、`execution_turnover_revaluation_*`
- 换手与参数实验：`turnover_control_experiment_*`、`execution_turnover_walk_forward_*`、`core_parameter_stability_*`
- 归因结果：`style_factor_attribution_*`、`style_timing_effectiveness_*`、`style_holding_exposure_quality_*`、`residual_attribution_*`
- 2026 案例：`case_2026_*`

### `output/cne6/images/`

```text
output/cne6/images/
|-- backtest/   # 主回测净值图、CNE6 因子累计收益图
|-- analysis/   # 风格归因、成本压力、residual 等分析图
|-- optimize/   # 换手控制、成交约束、参数稳定性实验图
`-- report/     # 最终报告专用图片
```

## 推荐运行顺序

如果已有基础缓存，常用顺序为：

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

## 版本管理备注

- `output/` 下有大量生成文件，其中部分超大 CSV 已在 `.gitignore` 中单独忽略。
- 不是所有 `output/` 文件都被忽略，提交前应检查 `git status`。
- 回测、优化和报告脚本通常会覆盖同名输出文件。
- CNE6 是当前主线，CNE5 保留为历史参考。
- 当前主报告聚焦 Alpha 精选版，但原始 `Barra Top100` 仍保留用于对照。

**最后更新：** 2026-06-03
