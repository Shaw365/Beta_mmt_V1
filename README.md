# BETA_MMT_V1：Barra CNE6 风格因子择时策略

本项目围绕 **Barra CNE6 风格因子择时选股策略** 展开，当前主线是：

1. 计算或读取 Barra CNE6 风格因子暴露、因子收益和价格数据；
2. 基于风格因子累计收益的通道位置生成风格择时信号；
3. 将择时信号映射为“理想风格向量”；
4. 选择风格暴露与理想向量最接近的股票；
5. 进行周频调仓回测，并输出绩效、交易记录和多维归因分析。

当前项目已经从单一回测脚本扩展为“回测 + 风格归因 + 择时有效性 + 持仓暴露质量 + 交易成本压力测试 + 因子剔除/降权实验 + residual 归因 + 策略报告”的研究框架。

## 当前主策略

当前 CNE6 主回测入口是：

```bash
python scripts/run_factor_timing_v3.py
```

该脚本当前使用的主要参数为：

```python
FactorTimingStrategy(
    long_prd=20,
    short_prd=5,
    channel_bins=2,
    extreme_value=1,
    top_n=100,
)
```

对应输出后缀为：

```text
l20_s5_b2_e1_n100
```

策略核心实现位于：

- `src/strategies/factor_timing_strategy_v3.py`
- `src/models/barra_cne6.py`

策略分析与诊断模块集中在 `src/analysis/`。

## 项目结构

```text
beta_mmt_v1/
├── src/
│   ├── models/
│   │   ├── barra_cne5.py
│   │   └── barra_cne6.py
│   ├── strategies/
│   │   ├── active_factor_screener.py
│   │   └── factor_timing_strategy_v3.py
│   ├── analysis/
│   │   ├── style_factor_attribution.py
│   │   ├── transaction_cost_stress.py
│   │   ├── factor_weight_experiment.py
│   │   └── residual_attribution.py
│   └── utils/
│       ├── benchmark.py
│       └── trade_recorder.py
├── scripts/
│   ├── run_factor_timing_v3.py
│   ├── run_factor_timing_cne5.py
│   ├── run_from_scratch.py
│   ├── regenerate_and_run.py
│   ├── run_style_factor_attribution_summary_cne6.py
│   ├── run_style_factor_attribution_regime_cne6.py
│   ├── run_style_timing_effectiveness_cne6.py
│   ├── run_style_holding_exposure_quality_cne6.py
│   ├── run_transaction_cost_stress_cne6.py
│   ├── run_factor_weight_experiment_cne6.py
│   ├── run_residual_attribution_cne6.py
│   └── render_strategy_report_pdf.py
├── docs/
│   ├── BETA_MMT_V1_CNE6风格择时策略报告.md
│   ├── BETA_MMT_V1_CNE6风格择时策略报告.pdf
│   ├── BETA_MMT_V1_CNE6风格择时策略报告_图文版.html
│   ├── BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf
│   ├── 项目完整复现文档.md
│   └── 项目详细说明文档.md
├── output/
│   └── cne6/
│       ├── data/
│       ├── images/
│       └── factor_timing_l20_s5_b2_e1_n100.png
├── prompt_doc/
│   └── 择时代码code.txt
├── PROJECT_STRUCTURE.md
├── requirements.txt
├── setup.py
└── README.md
```

更细的文件说明见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括：

- `pandas` / `numpy`
- `sqlalchemy` / `pymysql`
- `matplotlib` / `seaborn`
- `scipy` / `statsmodels`
- `openpyxl`

## 运行方式

### 1. 主回测

使用已有 CNE6 缓存数据运行：

```bash
python scripts/run_factor_timing_v3.py
```

典型输出：

- `output/cne6/data/portfolio_returns_l20_s5_b2_e1_n100.csv`
- `output/cne6/data/optimal_vectors_l20_s5_b2_e1_n100.csv`
- `output/cne6/data/交易记录_l20_s5_b2_e1_n100.xlsx`
- `output/cne6/data/annual_returns_l20_s5_b2_e1_n100.csv`
- `output/cne6/data/monthly_win_rate_l20_s5_b2_e1_n100.csv`
- `output/cne6/data/benchmark_relative_l20_s5_b2_e1_n100.csv`
- `output/cne6/factor_timing_l20_s5_b2_e1_n100.png`

### 2. 重新生成 Barra CNE6 数据并运行

```bash
python scripts/regenerate_and_run.py
```

`scripts/run_from_scratch.py` 目前仍保留了部分历史绝对路径写法，使用前建议先检查并改成当前项目路径。因此，当前更推荐使用 `run_factor_timing_v3.py` 和 `regenerate_and_run.py`。

### 3. 风格收益归因

全样本风格因子收益归因：

```bash
python scripts/run_style_factor_attribution_summary_cne6.py
```

分时段风格收益归因：

```bash
python scripts/run_style_factor_attribution_regime_cne6.py
```

当前分时段设置写在 `scripts/run_style_factor_attribution_regime_cne6.py` 中：

| 阶段 | 起始日 | 结束日 | 说明 |
|---|---:|---:|---|
| `steady_2020_to_2024_pre_jump` | 2020-02-17 | 2024-09-18 | 策略净值相对平稳期 |
| `jump_2024_q4` | 2024-09-23 | 2024-12-09 | 2024 年高收益阶段 |
| `jump_2025_mid` | 2025-04-07 | 2025-09-29 | 2025 年高收益阶段 |

### 4. 风格择时有效性与持仓暴露质量

风格择时有效性表：

```bash
python scripts/run_style_timing_effectiveness_cne6.py
```

持仓内部暴露质量表：

```bash
python scripts/run_style_holding_exposure_quality_cne6.py
```

这两类分析用于回答：

- 策略选出的股票组合，是否真的暴露在后续赚钱的风格方向上；
- 这种暴露是来自组合整体平均暴露，还是来自少数高暴露股票；
- 各风格因子的择时命中、正贡献和持仓兑现质量如何。

### 5. 交易成本压力测试

```bash
python scripts/run_transaction_cost_stress_cne6.py
```

默认测试单边成本：

```text
0bp, 5bp, 10bp, 20bp, 30bp, 50bp, 100bp
```

图中默认展示：

```text
0bp, 10bp, 20bp, 50bp, 100bp
```

### 6. 因子剔除/降权实验

```bash
python scripts/run_factor_weight_experiment_cne6.py
```

该实验用于观察剔除或降低部分风格因子权重后，对策略净值、回撤、换手和年度表现的影响。当前脚本包含：

- 原始全因子基准；
- 剔除 `TOPSI/STOQ/HISTVOL`；
- 剔除全样本负贡献因子；
- 问题因子降权；
- 核心贡献因子加权、问题因子降权；
- 仅保留核心和次级正贡献因子；
- 单因子剔除留一法。

### 7. Residual 归因

```bash
python scripts/run_residual_attribution_cne6.py
```

当前 residual 归因在没有行业分类字段的前提下，将组合收益拆成：

- 全市场等权共同项；
- 指数共同项；
- 风格模型可解释部分；
- 逐股 residual；
- 按信号日风格暴露分组的 residual 来源。

### 8. 策略报告生成

可编辑报告源文件：

```text
docs/BETA_MMT_V1_CNE6风格择时策略报告.md
```

生成图文版 HTML 和 PDF：

```bash
python scripts/render_strategy_report_pdf.py
```

输出：

- `docs/BETA_MMT_V1_CNE6风格择时策略报告_图文版.html`
- `docs/BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf`
- `docs/BETA_MMT_V1_CNE6风格择时策略报告.pdf`

该脚本使用本机 Chrome/Edge 的 headless 打印能力生成 PDF。为了避免污染项目目录，Chrome 临时 profile 会放在系统临时目录中，用完自动清理。

## 核心输出目录

### `output/cne6/data/`

主要包含：

- Barra CNE6 基础缓存：
  - `factor_exposure_cne6.csv`
  - `price_data_cne6.csv`
  - `factor_returns_cne6.csv`
  - `cumulative_returns_cne6.csv`
  - `factor_summary_cne6.xlsx`
  - `index_eod.csv`
- 主回测结果：
  - `portfolio_returns_l20_s5_b2_e1_n100.csv`
  - `optimal_vectors_l20_s5_b2_e1_n100.csv`
  - `annual_returns_l20_s5_b2_e1_n100.csv`
  - `monthly_win_rate_l20_s5_b2_e1_n100.csv`
  - `benchmark_relative_l20_s5_b2_e1_n100.csv`
  - `交易记录_l20_s5_b2_e1_n100.xlsx`
- 分析结果：
  - `style_factor_attribution_*`
  - `style_timing_effectiveness_*`
  - `style_holding_exposure_quality_*`
  - `transaction_cost_stress_*`
  - `factor_weight_experiment_*`
  - `residual_attribution_*`

### `output/cne6/images/`

主要包含：

- `cumulative_returns_cne6.png`
- `style_factor_attribution_summary_l20_s5_b2_e1_n100.png`
- `style_factor_attribution_regime_summary_l20_s5_b2_e1_n100.png`
- `style_timing_effectiveness_table_l20_s5_b2_e1_n100.png`
- `style_holding_exposure_quality_table_l20_s5_b2_e1_n100.png`
- `transaction_cost_stress_l20_s5_b2_e1_n100.png`
- `factor_weight_experiment_l20_s5_b2_e1_n100.png`
- `residual_attribution_l20_s5_b2_e1_n100.png`

## 数据源说明

代码中使用的数据库连接主要集中在：

- `src/models/barra_cne6.py`
- `src/models/barra_cne5.py`

涉及的数据源包括：

- `stock_market`
- `stock_finance`
- `stock_basic`
- 聚源 `jyzx`

数据库连接信息目前仍直接写在模型代码中。如果后续要提升可移植性，建议迁移到环境变量或本地配置文件。

## 当前状态与注意事项

- 当前主线是 CNE6；CNE5 代码保留为历史参考。
- 当前主策略结果后缀为 `l20_s5_b2_e1_n100`，分析模块默认读取这一组结果。
- `output/` 已在 `.gitignore` 中忽略，适合存放大体量缓存和回测结果。
- `factor_exposure_cne6.csv` 和 `price_data_cne6.csv` 体积较大，分析脚本中对暴露数据通常采用 chunk 方式读取。
- `run_from_scratch.py` 仍有历史绝对路径残留，建议后续单独清理。

## 参考文档

- [项目结构概览](PROJECT_STRUCTURE.md)
- [项目详细说明文档](docs/项目详细说明文档.md)
- [项目完整复现文档](docs/项目完整复现文档.md)
- [CNE6 风格择时策略报告](docs/BETA_MMT_V1_CNE6风格择时策略报告.md)
- [图文版策略报告 PDF](docs/BETA_MMT_V1_CNE6风格择时策略报告_图文版.pdf)

**最后更新：** 2026-04-30
