# 项目结构概览

本文档说明 `BETA_MMT_V1` 当前真实目录结构、核心模块、运行脚本和主要输出。项目当前主线是 **Barra CNE6 风格因子择时策略**。

## 顶层目录

```text
beta_mmt_v1/
├─ src/                    # 核心源码
├─ scripts/                # 可直接运行的脚本入口，按 backtest/analysis/optimize/report 分组
├─ docs/                   # 项目文档与策略报告
├─ output/                 # 回测、缓存和分析输出，已被 .gitignore 忽略
├─ prompt_doc/             # 历史参考资料
├─ README.md               # 项目总览
├─ PROJECT_STRUCTURE.md    # 当前文件
├─ requirements.txt        # Python 依赖
└─ setup.py                # 包配置
```

## 源码目录

```text
src/
├─ models/
│  ├─ barra_cne5.py
│  └─ barra_cne6.py
├─ strategies/
│  ├─ active_factor_screener.py
│  └─ factor_timing_strategy_v3.py
├─ analysis/
│  ├─ style_factor_attribution.py
│  ├─ transaction_cost_stress.py
│  ├─ factor_weight_experiment.py
│  └─ residual_attribution.py
├─ optimize/
│  └─ turnover_control_experiment.py
└─ utils/
   ├─ benchmark.py
   └─ trade_recorder.py
```

### `src/models/`

| 文件 | 作用 |
|---|---|
| `barra_cne6.py` | 当前主线 Barra CNE6 风格因子模型，生成因子暴露、因子收益、累计收益和基础缓存 |
| `barra_cne5.py` | CNE5 历史模型实现，当前主要作为保留参考 |

### `src/strategies/`

| 文件 | 作用 |
|---|---|
| `factor_timing_strategy_v3.py` | 主策略：风格择时信号、理想风格向量、相似度选股、周频回测、绩效图表和交易记录 |
| `active_factor_screener.py` | 主动因子二次筛选模块，当前不是主回测默认入口 |

### `src/analysis/`

| 文件 | 作用 |
|---|---|
| `style_factor_attribution.py` | 风格收益归因、分时段归因、择时有效性、持仓暴露质量分析 |
| `transaction_cost_stress.py` | 交易成本压力测试 |
| `factor_weight_experiment.py` | 因子剔除/降权实验 |
| `residual_attribution.py` | residual 归因 |

### `src/optimize/`

| 文件 | 作用 |
|---|---|
| `turnover_control_experiment.py` | 换手控制参数网格实验 |

### `src/utils/`

| 文件 | 作用 |
|---|---|
| `benchmark.py` | 读取指数数据，计算周频基准收益与相对收益 |
| `trade_recorder.py` | 记录调仓、买卖和持仓变化，导出交易记录 |

## 脚本目录

```text
scripts/
├─ backtest/
│  ├─ run_factor_timing_v3.py
│  ├─ run_factor_timing_cne5.py
│  ├─ run_from_scratch.py
│  └─ regenerate_and_run.py
├─ analysis/
│  ├─ run_style_factor_attribution_cne6.py
│  ├─ run_style_factor_attribution_summary_cne6.py
│  ├─ run_style_factor_attribution_regime_cne6.py
│  ├─ run_style_timing_effectiveness_cne6.py
│  ├─ run_style_holding_exposure_quality_cne6.py
│  ├─ run_transaction_cost_stress_cne6.py
│  └─ run_residual_attribution_cne6.py
├─ optimize/
│  ├─ run_factor_timing_turnover_control_cne6.py
│  ├─ run_turnover_control_experiment_cne6.py
│  └─ run_factor_weight_experiment_cne6.py
└─ report/
   └─ render_strategy_report_pdf.py
```

### 回测脚本

| 脚本 | 说明 |
|---|---|
| `scripts/backtest/run_factor_timing_v3.py` | 当前推荐的 CNE6 主回测入口，优先使用已有缓存 |
| `scripts/backtest/regenerate_and_run.py` | 重新生成 Barra CNE6 数据后运行主策略 |
| `scripts/backtest/run_factor_timing_cne5.py` | CNE5 历史回测脚本 |
| `scripts/backtest/run_from_scratch.py` | 历史完整流程入口，使用当前项目根目录下的 `output/cne6/` |

### 分析脚本

| 脚本 | 说明 |
|---|---|
| `scripts/analysis/run_style_factor_attribution_cne6.py` | 风格归因分析的历史整合入口 |
| `scripts/analysis/run_style_factor_attribution_summary_cne6.py` | 全样本风格因子收益归因 |
| `scripts/analysis/run_style_factor_attribution_regime_cne6.py` | 分时段风格因子收益归因，时段设置写在脚本内 |
| `scripts/analysis/run_style_timing_effectiveness_cne6.py` | 风格择时有效性分析 |
| `scripts/analysis/run_style_holding_exposure_quality_cne6.py` | 持仓内部风格暴露质量分析 |
| `scripts/analysis/run_transaction_cost_stress_cne6.py` | 交易成本压力测试 |
| `scripts/analysis/run_residual_attribution_cne6.py` | residual 归因 |

### 优化脚本

| 脚本 | 说明 |
|---|---|
| `scripts/optimize/run_factor_timing_turnover_control_cne6.py` | CNE6 换手控制版回测 |
| `scripts/optimize/run_turnover_control_experiment_cne6.py` | 换手控制参数网格实验 |
| `scripts/optimize/run_factor_weight_experiment_cne6.py` | 因子剔除/降权实验 |

### 报告脚本

| 脚本 | 说明 |
|---|---|
| `scripts/report/render_strategy_report_sample_style.py` | 将最终主文档 Markdown 策略报告渲染为样例风格 HTML/PDF |
| `scripts/report/render_strategy_report_pdf.py` | 将研究留痕版 Markdown 策略报告渲染为 HTML/PDF |

## 输出目录

`output/` 已经在 `.gitignore` 中忽略，用于保存大体量缓存、回测结果和分析图表。

```text
output/cne6/
├─ data/
└─ images/
   ├─ backtest/
   ├─ analysis/
   ├─ optimize/
   └─ report/
```

### `output/cne6/data/`

| 类型 | 文件示例 |
|---|---|
| Barra CNE6 基础缓存 | `factor_exposure_cne6.csv`、`price_data_cne6.csv`、`factor_returns_cne6.csv`、`cumulative_returns_cne6.csv` |
| 主策略结果 | `portfolio_returns_l20_s5_b2_e1_n100.csv`、`optimal_vectors_l20_s5_b2_e1_n100.csv`、`benchmark_relative_l20_s5_b2_e1_n100.csv` |
| 分析结果 | `style_factor_attribution_*`、`style_timing_effectiveness_*`、`style_holding_exposure_quality_*`、`transaction_cost_stress_*`、`residual_attribution_*` |
| 优化实验 | `factor_weight_experiment_*`、`turnover_control_experiment_*` |

### `output/cne6/images/`

| 子目录 | 内容 |
|---|---|
| `backtest/` | 主回测净值图、CNE6 风格因子累计收益图 |
| `analysis/` | 风格归因、分时段归因、择时有效性、持仓暴露质量、成本压力测试、residual 归因 |
| `optimize/` | 因子剔除/降权实验、换手控制实验 |
| `report/` | 报告专用图片预留目录 |

## 快速运行顺序

如果已有 `output/cne6/data/` 缓存，推荐顺序为：

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

## 当前状态备注

- CNE6 是当前主线，CNE5 保留为历史参考。
- 分析模块默认绑定 `l20_s5_b2_e1_n100` 这一组主策略输出。
- `output/` 中包含大文件，不应纳入版本管理。
- 历史回测脚本已经随本次目录调整改为使用当前项目根目录下的 `output/`。

**最后更新：** 2026-04-30
