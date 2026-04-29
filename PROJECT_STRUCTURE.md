# 项目结构概览

## 目录结构

```text
beta_mmt_v1/
├── src/                              # 核心源码
│   ├── __init__.py
│   ├── models/                       # Barra 模型
│   │   ├── __init__.py
│   │   ├── barra_cne5.py
│   │   └── barra_cne6.py
│   ├── strategies/                   # 策略模块
│   │   ├── __init__.py
│   │   ├── active_factor_screener.py
│   │   └── factor_timing_strategy_v3.py
│   └── utils/                        # 工具模块
│       ├── __init__.py
│       ├── benchmark.py
│       └── trade_recorder.py
├── scripts/                          # 运行脚本
│   ├── run_factor_timing_v3.py
│   ├── run_factor_timing_cne5.py
│   ├── run_from_scratch.py
│   └── regenerate_and_run.py
├── docs/                             # 项目文档
│   ├── 项目详细说明文档.md
│   └── 项目完整复现文档.md
├── output/                           # 输出目录
│   ├── README.md
│   ├── cne5/
│   └── cne6/
│       ├── data/
│       └── images/
├── prompt_doc/                       # 参考资料
│   └── 择时代码code.txt
├── PROJECT_STRUCTURE.md
├── README.md
├── requirements.txt
└── setup.py
```

## 文件统计

只统计当前仓库内可见的主要源码与文档文件，不含 `__pycache__` 与输出结果文件：

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `src/models/` | 3 | `__init__.py` + 2 个 Barra 模型 |
| `src/strategies/` | 3 | `__init__.py` + 2 个策略相关模块 |
| `src/utils/` | 3 | `__init__.py` + 基准与交易记录工具 |
| `scripts/` | 4 | 4 个运行脚本 |
| `docs/` | 2 | 2 份中文文档 |
| `prompt_doc/` | 1 | 1 份参考资料 |
| 根目录 | 4 | `README.md`、`PROJECT_STRUCTURE.md`、`requirements.txt`、`setup.py` |

## 快速开始

### 1. 安装依赖

```bash
cd e:/code/beta_mmt_v1
pip install -r requirements.txt
```

### 2. 运行主策略

使用缓存数据运行：

```bash
python scripts/run_factor_timing_v3.py
```

重新生成 Barra 数据后运行：

```bash
python scripts/regenerate_and_run.py
```

完整流程入口：

```bash
python scripts/run_from_scratch.py
python scripts/run_from_scratch.py --force
```

## 文档导航

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 项目总览与当前仓库状态说明 |
| [docs/项目详细说明文档.md](docs/项目详细说明文档.md) | 详细技术说明 |
| [docs/项目完整复现文档.md](docs/项目完整复现文档.md) | 完整复现说明 |
| [output/README.md](output/README.md) | 输出目录说明 |
| [prompt_doc/择时代码code.txt](prompt_doc/择时代码code.txt) | 择时逻辑参考 |

## 核心模块

### 1. Barra 模型：`src/models/`

#### `barra_cne6.py`

- 当前仓库主线模型
- 计算 25 个 CNE6 风格因子
- 生成因子暴露、因子收益率、累计收益率和汇总 Excel
- 为择时策略提供 `factor_exposure_cne6.csv` 与 `price_data_cne6.csv`

示例：

```python
from src.models.barra_cne6 import BarraCNE6

barra = BarraCNE6(start_date="2020-01-01", end_date="2025-12-31")
factor_returns_df, cumulative_returns_df = barra.run()
```

#### `barra_cne5.py`

- 保留 CNE5 模型实现
- 当前文件内仍存在历史绝对路径写法
- 可作为参考代码，但与当前仓库目录并非完全自洽

### 2. 策略模块：`src/strategies/`

#### `factor_timing_strategy_v3.py`

- 预计算周度收益率
- 基于因子累计收益率生成通道分档信号
- 构造最优因子向量
- 按余弦相似度选股
- 统计收益、回撤、胜率、换手率，并输出图表与交易记录

示例：

```python
from src.strategies.factor_timing_strategy_v3 import FactorTimingStrategy

strategy = FactorTimingStrategy(
    long_prd=60,
    short_prd=10,
    channel_bins=2,
    extreme_value=2,
    top_n=100
)
```

#### `active_factor_screener.py`

- 供二次筛选场景使用的主动因子筛选模块
- 当前主脚本未默认启用

### 3. 工具模块：`src/utils/`

#### `benchmark.py`

- 读取基准指数数据
- 计算周度基准收益与策略相对收益

#### `trade_recorder.py`

- 记录调仓结果
- 导出 `交易记录_{suffix}.xlsx`

## 当前主流程

当前仓库最自洽、推荐使用的是 `CNE6` 主流程：

1. `scripts/run_factor_timing_v3.py`
2. `src/models/barra_cne6.py`
3. `src/strategies/factor_timing_strategy_v3.py`
4. 输出到 `output/cne6/`

该主流程会生成：

- `output/cne6/data/portfolio_returns_{suffix}.csv`
- `output/cne6/data/optimal_vectors_{suffix}.csv`
- `output/cne6/data/交易记录_{suffix}.xlsx`
- `output/cne6/data/annual_returns_{suffix}.csv`
- `output/cne6/data/monthly_win_rate_{suffix}.csv`
- `output/cne6/data/benchmark_relative_{suffix}.csv`
- `output/cne6/factor_timing_{suffix}.png`

## 当前仓库与旧文档相比的关键状态

- 项目根目录实际为 `beta_mmt_v1`，不是 `beta_mmt`
- `docs/` 目前只有 2 个文档，不存在 `USER_MANUAL.md`、`QUICKSTART.md` 等旧文件
- `prompt_doc/` 目前只有 `择时代码code.txt`
- `src/strategies/` 实际包含 `active_factor_screener.py`
- `src/utils/` 实际包含 `benchmark.py` 与 `trade_recorder.py`
- CNE5 相关代码仍保留，但有旧路径残留

---

**最后更新：** 2026-04-28
