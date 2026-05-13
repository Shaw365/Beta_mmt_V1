# BETA_MMT_V1：Barra CNE6 风格因子择时策略

本项目围绕 **Barra CNE6 风格因子择时选股策略** 展开，当前主线是：

1. 从数据库或本地缓存生成 Barra CNE6 风格因子暴露、因子收益、价格和指数数据；
2. 基于风格因子累计收益通道生成风格择时信号；
3. 将信号映射为当期“理想风格向量”；
4. 在股票截面中选择风格暴露与理想向量最接近的股票；
5. 进行周频调仓回测，并继续评估交易成本、ADV 成交约束、换手控制、容量、归因和参数稳定性；
6. 输出最终策略报告、研究留痕报告、图表和 CSV 明细。

当前定稿研究口径为：

```text
核心参数：L20 / S5 / B2 / E1 / N100
执行层：tc50_buf2
成本口径：10bp 双边固定成本 + 首期建仓 + ADV 冲击成本
主样本：2020-02-17 ~ 2025-12-22
补充案例：2026-01-05 ~ 2026-05-06
```

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括 `pandas`、`numpy`、`sqlalchemy`、`pymysql`、`matplotlib`、`seaborn`、`scipy`、`statsmodels`、`openpyxl`。

部分脚本会访问内网 MySQL 数据库，数据库连接目前写在 `src/models/barra_cne6.py`、`src/utils/benchmark.py` 等模块中；如果只基于已有 `output/cne6/data/` 缓存运行，则不一定需要重新访问数据库。

## 快速入口

主策略回测：

```bash
python scripts/backtest/run_factor_timing_v3.py
```

最终主报告渲染：

```bash
python scripts/report/render_strategy_report_sample_style.py
```

2026 年案例分析数据与图片：

```bash
python scripts/report/build_2026_case_analysis.py
```

最终主报告文件：

```text
docs/BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.md
docs/BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.html
docs/BETA_MMT_V1_CNE6风格择时策略报告_最终主文档.pdf
```

研究留痕版报告文件：

```text
docs/BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.md
docs/BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.html
docs/BETA_MMT_V1_CNE6风格择时策略报告_研究留痕版.pdf
```

## 当前项目结构

```text
beta_mmt_v1/
├─ src/                    # 核心源码
│  ├─ models/              # Barra CNE5/CNE6 因子模型
│  ├─ strategies/          # 风格择时、相似度选股、周频回测
│  ├─ analysis/            # 归因、成本压力、因子权重实验
│  ├─ optimize/            # 换手控制、成交约束、参数稳定性实验
│  └─ utils/               # 指数基准、交易记录等工具
├─ scripts/                # 可直接运行的脚本入口
│  ├─ backtest/
│  ├─ analysis/
│  ├─ optimize/
│  └─ report/
├─ docs/                   # 项目文档与策略报告
├─ output/                 # 缓存、回测、分析图表和报告图片
├─ prompt_doc/             # 历史参考资料
├─ PROJECT_STRUCTURE.md    # 更细的目录说明
├─ requirements.txt
└─ setup.py
```

更细的文件说明见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

## 常用脚本

### 回测

```bash
python scripts/backtest/run_factor_timing_v3.py
python scripts/backtest/regenerate_and_run.py
python scripts/backtest/run_factor_timing_cne5.py
python scripts/backtest/run_from_scratch.py
```

`run_factor_timing_v3.py` 是当前推荐的 CNE6 主回测入口，默认优先使用本地缓存。`regenerate_and_run.py` 会重新生成 Barra CNE6 数据并覆盖相关缓存，运行前应确认数据库可访问。

### 分析

```bash
python scripts/analysis/run_style_factor_attribution_summary_cne6.py
python scripts/analysis/run_style_factor_attribution_regime_cne6.py
python scripts/analysis/run_style_timing_effectiveness_cne6.py
python scripts/analysis/run_style_holding_exposure_quality_cne6.py
python scripts/analysis/run_transaction_cost_stress_cne6.py
python scripts/analysis/run_residual_attribution_cne6.py
```

这些脚本主要消费 `output/cne6/data/portfolio_returns_l20_s5_b2_e1_n100.csv`、`factor_returns_cne6.csv`、`price_data_cne6.csv` 等缓存，并输出归因、成本和 residual 分析结果。

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
python scripts/report/render_strategy_report_sample_style.py
python scripts/report/render_strategy_report_pdf.py
```

- `build_final_report_figures.py`：生成最终报告专用图表；
- `build_2026_case_analysis.py`：生成 2026 案例分析数据和图 8/图 9；
- `render_strategy_report_sample_style.py`：渲染最终主文档 HTML/PDF；
- `render_strategy_report_pdf.py`：渲染研究留痕版 HTML/PDF。

## 核心输出

### `output/cne6/data/`

主要包含：

- 基础缓存：`factor_exposure_cne6.csv`、`price_data_cne6.csv`、`factor_returns_cne6.csv`、`cumulative_returns_cne6.csv`、`index_eod.csv`
- 主回测结果：`portfolio_returns_l20_s5_b2_e1_n100.csv`、`optimal_vectors_l20_s5_b2_e1_n100.csv`、`benchmark_relative_l20_s5_b2_e1_n100.csv`
- 成本与成交：`transaction_cost_*`、`execution_capacity_*`、`execution_turnover_revaluation_*`
- 换手与参数实验：`turnover_control_experiment_*`、`execution_turnover_walk_forward_*`、`core_parameter_stability_*`
- 归因结果：`style_factor_attribution_*`、`style_timing_effectiveness_*`、`style_holding_exposure_quality_*`、`residual_attribution_*`
- 2026 案例：`case_2026_*`

### `output/cne6/images/`

```text
output/cne6/images/
├─ backtest/   # 主回测净值图、CNE6 因子累计收益图
├─ analysis/   # 风格归因、成本压力、residual 等分析图片
├─ optimize/   # 换手控制、成交约束、参数稳定性实验图片
└─ report/     # 最终报告专用图片，包括 2026 案例图
```

## 推荐运行顺序

如果已有基础缓存，常用顺序为：

```bash
python scripts/backtest/run_factor_timing_v3.py
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
python scripts/report/build_final_report_figures.py
python scripts/report/build_2026_case_analysis.py
python scripts/report/render_strategy_report_sample_style.py
```

## 版本管理备注

- `output/` 下有大量生成文件，其中部分超大 CSV 已在 `.gitignore` 中单独忽略；
- 不是所有 `output/` 文件都被忽略，提交前应检查 `git status`；
- 回测和优化脚本通常会覆盖同名输出文件；
- CNE6 是当前主线，CNE5 保留为历史参考。

**最后更新：** 2026-05-13
