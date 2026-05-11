# BETA_MMT_V1：Barra CNE6 风格因子择时策略

本项目围绕 **Barra CNE6 风格因子择时选股策略** 展开。当前主线包括：

1. 生成或读取 Barra CNE6 风格因子暴露、因子收益、价格和指数缓存；
2. 基于风格因子累计收益的通道位置生成风格择时信号；
3. 将择时信号映射为“理想风格向量”；
4. 选择风格暴露与理想向量最接近的股票；
5. 周频调仓回测，并输出绩效、交易记录、归因、优化实验和报告。

当前项目已经按用途拆成四类脚本：`backtest`、`analysis`、`optimize`、`report`。图片输出也按同样逻辑归入 `output/cne6/images/` 下的分类目录。

## 快速运行

主策略回测：

```bash
python scripts/backtest/run_factor_timing_v3.py
```

当前核心参数：

```python
FactorTimingStrategy(
    long_prd=20,
    short_prd=5,
    channel_bins=2,
    extreme_value=1,
    top_n=100,
)
```

对应输出后缀：

```text
l20_s5_b2_e1_n100
```

换手控制版回测：

```bash
python scripts/optimize/run_factor_timing_turnover_control_cne6.py
```

换手控制参数网格实验：

```bash
python scripts/optimize/run_turnover_control_experiment_cne6.py
```

## 项目结构

```text
beta_mmt_v1/
├─ src/
│  ├─ models/
│  │  ├─ barra_cne5.py
│  │  └─ barra_cne6.py
│  ├─ strategies/
│  │  ├─ active_factor_screener.py
│  │  └─ factor_timing_strategy_v3.py
│  ├─ analysis/
│  │  ├─ style_factor_attribution.py
│  │  ├─ transaction_cost_stress.py
│  │  ├─ factor_weight_experiment.py
│  │  └─ residual_attribution.py
│  ├─ optimize/
│  │  └─ turnover_control_experiment.py
│  └─ utils/
│     ├─ benchmark.py
│     └─ trade_recorder.py
├─ scripts/
│  ├─ backtest/
│  │  ├─ run_factor_timing_v3.py
│  │  ├─ run_factor_timing_cne5.py
│  │  ├─ run_from_scratch.py
│  │  └─ regenerate_and_run.py
│  ├─ analysis/
│  │  ├─ run_style_factor_attribution_cne6.py
│  │  ├─ run_style_factor_attribution_summary_cne6.py
│  │  ├─ run_style_factor_attribution_regime_cne6.py
│  │  ├─ run_style_timing_effectiveness_cne6.py
│  │  ├─ run_style_holding_exposure_quality_cne6.py
│  │  ├─ run_transaction_cost_stress_cne6.py
│  │  └─ run_residual_attribution_cne6.py
│  ├─ optimize/
│  │  ├─ run_factor_timing_turnover_control_cne6.py
│  │  ├─ run_turnover_control_experiment_cne6.py
│  │  └─ run_factor_weight_experiment_cne6.py
│  └─ report/
│     └─ render_strategy_report_pdf.py
├─ docs/
├─ output/
│  └─ cne6/
│     ├─ data/
│     └─ images/
│        ├─ backtest/
│        ├─ analysis/
│        ├─ optimize/
│        └─ report/
├─ PROJECT_STRUCTURE.md
├─ requirements.txt
└─ setup.py
```

更细的文件说明见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括 `pandas`、`numpy`、`sqlalchemy`、`pymysql`、`matplotlib`、`seaborn`、`scipy`、`statsmodels`、`openpyxl`。

## 常用脚本

### 回测

```bash
python scripts/backtest/run_factor_timing_v3.py
python scripts/backtest/regenerate_and_run.py
python scripts/backtest/run_factor_timing_cne5.py
```

`scripts/backtest/run_from_scratch.py` 是历史完整流程入口，已改为使用当前项目根目录下的 `output/cne6/`。

### 分析

```bash
python scripts/analysis/run_style_factor_attribution_summary_cne6.py
python scripts/analysis/run_style_factor_attribution_regime_cne6.py
python scripts/analysis/run_style_timing_effectiveness_cne6.py
python scripts/analysis/run_style_holding_exposure_quality_cne6.py
python scripts/analysis/run_transaction_cost_stress_cne6.py
python scripts/analysis/run_residual_attribution_cne6.py
```

分时段收益归因的区间设置写在 `scripts/analysis/run_style_factor_attribution_regime_cne6.py` 中。

### 优化实验

```bash
python scripts/optimize/run_factor_timing_turnover_control_cne6.py
python scripts/optimize/run_turnover_control_experiment_cne6.py
python scripts/optimize/run_factor_weight_experiment_cne6.py
```

### 报告

```bash
python scripts/report/render_strategy_report_pdf.py
```

该脚本读取 `docs/BETA_MMT_V1_CNE6风格择时策略报告.md`，并生成图文版 HTML/PDF。报告中的图片引用会从新的分类图片目录读取。

## 核心输出目录

### `output/cne6/data/`

主要包含：

- Barra CNE6 基础缓存：`factor_exposure_cne6.csv`、`price_data_cne6.csv`、`factor_returns_cne6.csv`、`cumulative_returns_cne6.csv`、`factor_summary_cne6.xlsx`、`index_eod.csv`
- 主回测结果：`portfolio_returns_*`、`optimal_vectors_*`、`annual_returns_*`、`monthly_win_rate_*`、`benchmark_relative_*`、`交易记录_*`
- 分析和优化结果：`style_factor_attribution_*`、`style_timing_effectiveness_*`、`style_holding_exposure_quality_*`、`transaction_cost_stress_*`、`factor_weight_experiment_*`、`residual_attribution_*`、`turnover_control_experiment_*`

### `output/cne6/images/`

按用途分为：

- `backtest/`：主回测净值图、CNE6 风格因子累计收益图
- `analysis/`：风格归因、分时段归因、择时有效性、持仓暴露质量、交易成本压力测试、residual 归因
- `optimize/`：因子剔除/降权实验、换手控制实验
- `report/`：后续如有报告专用图片，可放在这里

## 推荐运行顺序

如果已经有 `output/cne6/data/` 缓存，推荐顺序为：

```bash
python scripts/backtest/run_factor_timing_v3.py
python scripts/optimize/run_factor_timing_turnover_control_cne6.py
python scripts/analysis/run_style_factor_attribution_summary_cne6.py
python scripts/analysis/run_style_factor_attribution_regime_cne6.py
python scripts/analysis/run_style_timing_effectiveness_cne6.py
python scripts/analysis/run_style_holding_exposure_quality_cne6.py
python scripts/analysis/run_transaction_cost_stress_cne6.py
python scripts/optimize/run_factor_weight_experiment_cne6.py
python scripts/analysis/run_residual_attribution_cne6.py
python scripts/optimize/run_turnover_control_experiment_cne6.py
python scripts/report/render_strategy_report_pdf.py
```

## 当前状态

- CNE6 是当前主线，CNE5 保留为历史参考。
- 主策略默认结果后缀为 `l20_s5_b2_e1_n100`。
- `output/` 已在 `.gitignore` 中忽略，适合存放大体量缓存和回测结果。
- 数据库连接目前仍直接写在模型代码中，后续如需提升可移植性，建议迁移到环境变量或本地配置文件。

**最后更新：** 2026-04-30
