# Barra风格因子择时策略

基于 Barra 风格因子模型的择时与选股项目。当前仓库以 `CNE6 + 周度换仓择时策略` 为主线，包含：

- Barra CNE6 风格因子计算
- 基于因子累计收益率通道位置的择时信号生成
- 基于最优因子向量与股票因子暴露余弦相似度的选股
- 周度换仓、交易记录、绩效统计与基准对比输出

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
│   └── utils/
│       ├── benchmark.py
│       └── trade_recorder.py
├── scripts/
│   ├── regenerate_and_run.py
│   ├── run_factor_timing_cne5.py
│   ├── run_factor_timing_v3.py
│   └── run_from_scratch.py
├── docs/
│   ├── 项目完整复现文档.md
│   └── 项目详细说明文档.md
├── output/
│   ├── README.md
│   ├── cne5/
│   └── cne6/
├── prompt_doc/
│   └── 择时代码code.txt
├── PROJECT_STRUCTURE.md
├── requirements.txt
├── setup.py
└── README.md
```

## 核心模块

### 1. Barra CNE6 模型

`src/models/barra_cne6.py` 实现了 25 个风格因子：

| 类别 | 因子 |
|------|------|
| 规模 | SIZE, MIDCAP |
| 波动率 | BETA, RESVOL, HISTVOL |
| 动量 | MOMENTUM, RESMOM |
| 价值 | BTOP, EYIELD, CFP, SP, LP |
| 成长 | EGRO, SGRO |
| 杠杆 | MLEV, BLEV |
| 流动性 | LIQUIDITY, STOM, STOQ |
| 盈利质量 | ROE, ROA |
| 投资 | CAPX, AGRO |
| 其他 | TOPSI, SEASON |

默认建模区间在实际运行脚本中通常设为：

```python
BarraCNE6(start_date="2020-01-01", end_date="2025-12-31")
```

### 2. 择时策略

`src/strategies/factor_timing_strategy_v3.py` 的核心流程为：

```text
因子累计收益率
→ 通道位置分档信号
→ 最优因子向量（通道外极端信号按 extreme_value 放大）
→ 股票因子暴露与最优向量做余弦相似度
→ 选出 Top N 股票
→ 周度换仓并统计收益、回撤、换手率
```

策略实现细节与当前代码一致：

- 使用前一个交易日的因子暴露做选股，避免偷看未来数据
- ST 股票在数据源查询阶段被排除
- 停牌股票在换仓时动态过滤
- 支持输出交易记录、年度收益率、月度胜率、基准相对收益

### 3. 默认参数

当前主运行脚本 `scripts/run_factor_timing_v3.py` 的默认参数为：

```python
strategy = FactorTimingStrategy(
    long_prd=60,
    short_prd=10,
    channel_bins=2,
    extreme_value=2,
    top_n=100
)
```

`FactorTimingStrategy` 类本身的构造默认值仍是：

```python
FactorTimingStrategy(
    long_prd=20,
    short_prd=5,
    channel_bins=3,
    extreme_value=3,
    top_n=100
)
```

也就是说，实际运行时应以脚本传入参数为准。

`extreme_value` 当前用于放大通道外的极端择时信号：`+1/-1` 会映射为
`+extreme_value/-extreme_value`，通道内分档信号保持原始强度。这样该参数会改变
余弦相似度中极端因子与通道内因子的相对权重。若希望得到与旧版整体缩放逻辑
等价的效果，请设置 `extreme_value=1`。

## 运行方式

### 安装依赖

```bash
pip install -r requirements.txt
```

### 推荐运行：CNE6 择时策略

使用已有缓存数据运行：

```bash
python scripts/run_factor_timing_v3.py
```

重新生成 Barra 数据后再运行：

```bash
python scripts/regenerate_and_run.py
```

完整流程入口：

```bash
python scripts/run_from_scratch.py
python scripts/run_from_scratch.py --force
```

### CNE5 相关说明

仓库中保留了 `CNE5` 的模型与策略脚本：

- `src/models/barra_cne5.py`
- `scripts/run_factor_timing_cne5.py`

但这些文件当前仍包含历史遗留的绝对路径写法，默认输出目录并不指向本仓库根目录下的 `output/cne5/`。因此它们在“当前仓库即开即用”层面不如 CNE6 主流程一致。

## 输出结果

当前仓库内已经存在多组 CNE6 输出，主要位于：

- `output/cne6/data/`
- `output/cne6/`

主策略脚本 `scripts/run_factor_timing_v3.py` 会生成以下文件：

- `output/cne6/data/portfolio_returns_{suffix}.csv`
- `output/cne6/data/optimal_vectors_{suffix}.csv`
- `output/cne6/data/交易记录_{suffix}.xlsx`
- `output/cne6/data/annual_returns_{suffix}.csv`
- `output/cne6/data/monthly_win_rate_{suffix}.csv`
- `output/cne6/data/benchmark_relative_{suffix}.csv`
- `output/cne6/factor_timing_{suffix}.png`

其中参数后缀格式为：

```text
l{long_prd}_s{short_prd}_b{channel_bins}_e{extreme_value}_n{top_n}
```

仓库当前可见的示例后缀包括：

- `l60_s10_b2_e2_n100`
- `l30_s5_b2_e2_n100`
- `l20_s5_b5_e3_n100`
- `l20_s5_b3_e3_n100`
- `l20_s5_b2_e3_n100`
- `l20_s5_b2_e2_n100`

另外，Barra CNE6 模型还会生成基础缓存与汇总文件：

- `output/cne6/data/factor_exposure_cne6.csv`
- `output/cne6/data/price_data_cne6.csv`
- `output/cne6/data/factor_returns_cne6.csv`
- `output/cne6/data/cumulative_returns_cne6.csv`
- `output/cne6/data/factor_summary_cne6.xlsx`
- `output/cne6/data/index_eod.csv`

## 数据源

代码中实际使用了以下数据库连接：

- `stock_market`
- `stock_finance`
- `stock_basic`
- 聚源 `jyzx`

数据库连接字符串直接写在：

- `src/models/barra_cne6.py`
- `src/models/barra_cne5.py`

当前仓库中不存在 `prompt_doc/数据库连接文件说明.txt`，`prompt_doc` 目录下现有文件只有：

- `prompt_doc/择时代码code.txt`

## 参考文档

- [项目详细说明文档](docs/项目详细说明文档.md)
- [项目完整复现文档](docs/项目完整复现文档.md)
- [项目结构概览](PROJECT_STRUCTURE.md)
- [输出目录说明](output/README.md)
- [择时代码参考](prompt_doc/择时代码code.txt)

## 当前仓库状态备注

- CNE6 主流程与当前仓库目录基本一致，可作为主要使用入口
- CNE5 代码仍有旧项目路径残留
- `output/cne6/` 下已存在历史运行结果，可直接用于查看文件格式与结果样例

**更新时间：** 2026-04-28
