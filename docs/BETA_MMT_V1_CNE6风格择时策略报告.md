# BETA_MMT_V1 CNE6 风格择时策略报告

报告日期：2026-04-30  
研究对象：`BETA_MMT_V1` 项目中的 Barra CNE6 风格因子择时选股策略  
回测区间：2020-02-17 至 2025-12-22  
当前参数：`long_prd=20, short_prd=5, channel_bins=2, extreme_value=1, top_n=100`  
主要输出后缀：`l20_s5_b2_e1_n100`

> 说明：本报告是一份可编辑的研究文档，结论基于当前本地缓存数据、当前代码逻辑和已生成的分析输出。报告中的数值均为样本内回测及样本内诊断结果，不构成实盘投资建议。

## 1. 执行摘要

当前 CNE6 风格择时策略在样本内表现非常强：期末净值 `8.01`，累计收益 `700.6%`，年化收益 `42.7%`，年化波动 `28.7%`，最大回撤 `-18.0%`，胜率 `60.1%`。相对中证500和中证1000均有显著超额，期末累计超额分别约为 `517.3%` 和 `541.5%`。

不过，策略收益并不完全来自 Barra 风格择时本身。风格因子解释了约 `54.2%` 的算术收益，residual 解释了约 `45.8%`。进一步拆解 residual 后发现，其中大部分接近全市场等权共同项：全市场等权收益贡献 `94.8%`，扣除全市场等权后的选股残差只有 `11.4%`，约占策略总收益 `4.9%`。因此，策略更准确的描述是：

> 以 CNE6 风格择时为核心选股约束，同时显著受益于小市值、高弹性股票共同行情的周度换仓策略。

交易成本是策略落地的关键约束。平均单边换手约 `76.9%`，在单边 `20bp` 成本假设下，年化收益从 `42.7%` 降至 `31.9%`，仍有吸引力；在 `50bp` 下年化收益降至 `17.1%`，夏普降至 `0.49`；在 `100bp` 下策略转为负年化。也就是说，策略对中低成本环境仍有韧性，但对高交易成本非常敏感。

因子层面，`LIQUIDITY`、`SIZE`、`BETA`、`RESVOL` 是主要收益来源；其中 `LIQUIDITY` 是最稳定的方向型收益来源，`SIZE` 兼具信号有效性和持仓内部兑现质量。`TOPSI`、`STOQ`、`HISTVOL` 在归因上偏弱或为负，但简单剔除/降权并没有改善策略表现，说明因子间存在显著交互，不能只按单因子样本内贡献做机械删减。

本报告建议下一阶段优先做三件事：

1. 引入换手缓冲或交易成本约束，降低实盘摩擦。
2. 做滚动可靠性加权，而不是全样本事后因子剔除。
3. 补充行业分类缓存，进一步拆解 residual 中的行业和主题暴露。

## 2. 项目架构概览

项目结构大致分为四层：

| 层级 | 路径 | 作用 |
|---|---|---|
| Barra 模型层 | `src/models/barra_cne6.py` | 生成 CNE6 风格因子暴露、因子收益和累计因子收益 |
| 策略回测层 | `src/strategies/factor_timing_strategy_v3.py` | 生成择时信号、最优风格向量、余弦相似度选股、周度回测 |
| 分析诊断层 | `src/analysis/` | 收益归因、交易成本压力测试、因子剔除/降权实验、residual 归因 |
| 脚本入口层 | `scripts/` | 组织不同分析任务的可复现入口 |

当前主要入口如下：

| 脚本 | 作用 |
|---|---|
| `scripts/run_factor_timing_v3.py` | 运行 CNE6 风格择时主策略 |
| `scripts/run_style_factor_attribution_cne6.py` | 生成完整风格归因、分时段归因、择时有效性、持仓暴露质量 |
| `scripts/run_style_factor_attribution_summary_cne6.py` | 只生成全样本风格收益归因 |
| `scripts/run_style_factor_attribution_regime_cne6.py` | 只生成分时段风格收益归因 |
| `scripts/run_style_timing_effectiveness_cne6.py` | 生成风格择时有效性表 |
| `scripts/run_style_holding_exposure_quality_cne6.py` | 生成持仓内部风格暴露质量表 |
| `scripts/run_transaction_cost_stress_cne6.py` | 生成交易成本压力测试 |
| `scripts/run_factor_weight_experiment_cne6.py` | 生成因子剔除/降权实验 |
| `scripts/run_residual_attribution_cne6.py` | 生成 residual 归因 |

## 3. 策略逻辑

策略主流程如下：

```text
CNE6 因子累计收益
→ 计算每个风格因子的通道位置
→ 生成风格择时信号
→ 得到“理想风格向量”
→ 用股票 CNE6 暴露与理想风格向量计算余弦相似度
→ 选取相似度最高的 100 只股票
→ 等权持有一周
→ 每周换仓
```

当前参数来自 `scripts/run_factor_timing_v3.py`：

```python
FactorTimingStrategy(
    long_prd=20,
    short_prd=5,
    channel_bins=2,
    extreme_value=1,
    top_n=100,
)
```

关键实现细节：

- 信号使用因子累计收益通道位置生成。
- 选股使用前一个交易日的因子暴露，避免偷看未来。
- 停牌股票在换仓时动态过滤。
- 组合等权持有，目标持仓数量为 100。
- 换手率为单边换手率，即卖出股票数 / 上期持仓股票数。

## 4. 回测表现

### 4.1 总体表现

| 指标 | 数值 |
|---|---:|
| 回测起点 | 2020-02-17 |
| 回测终点 | 2025-12-22 |
| 周度期数 | 301 |
| 期末净值 | 8.01 |
| 累计收益 | 700.6% |
| 年化收益 | 42.7% |
| 年化波动 | 28.7% |
| 夏普比率 | 1.38 |
| 最大回撤 | -18.0% |
| 周度胜率 | 60.1% |
| 平均持仓 | 100 |
| 平均单边换手 | 76.9% |
| 中位数单边换手 | 79.0% |

对应图表：

- `output/cne6/factor_timing_l20_s5_b2_e1_n100.png`
- `output/cne6/images/cumulative_returns_cne6.png`

### 4.2 年度表现

| 年份 | 年度收益率 | 年化波动率 | 夏普比率 | 胜率 | 最大回撤 |
|---|---:|---:|---:|---:|---:|
| 2020 | 38.56% | 25.61% | 1.40 | 58.70% | 11.25% |
| 2021 | 74.45% | 18.87% | 3.79 | 65.38% | 7.45% |
| 2022 | 18.06% | 21.61% | 0.70 | 56.00% | 9.75% |
| 2023 | 20.93% | 19.15% | 0.94 | 54.00% | 11.23% |
| 2024 | 22.48% | 49.97% | 0.39 | 55.77% | 16.99% |
| 2025 | 89.40% | 24.53% | 3.53 | 70.59% | 12.36% |

2024 年是风险特征最突出的年份：收益仍为正，但年化波动接近 `50%`，夏普显著降低，说明该年度策略经历了较强的风格或市场冲击。

### 4.3 基准对比

截至 2025-12-22：

| 指标 | 数值 |
|---|---:|
| 策略净值 | 8.01 |
| 中证500净值 | 1.30 |
| 中证1000净值 | 1.25 |
| 相对中证500累计超额 | 517.3% |
| 相对中证1000累计超额 | 541.5% |

需要注意，相对指数超额并不等同于纯 alpha。后文 residual 归因显示，策略受益于全市场等权共同项，尤其是小市值股票共同行情。

## 5. 风格收益归因

全样本算术归因结果：

| 组件 | 累计贡献 | 策略算术收益占比 |
|---|---:|---:|
| 风格因子合计 | 125.8% | 54.2% |
| Residual | 106.3% | 45.8% |
| 策略合计 | 232.1% | 100.0% |

主要风格因子贡献：

| 因子 | 累计贡献 | 策略算术收益占比 |
|---|---:|---:|
| LIQUIDITY | 45.9% | 19.8% |
| SIZE | 23.2% | 10.0% |
| BETA | 22.7% | 9.8% |
| RESVOL | 20.1% | 8.7% |
| RESMOM | 11.1% | 4.8% |
| MIDCAP | 10.7% | 4.6% |
| CAPX | 10.3% | 4.4% |
| SEASON | 5.7% | 2.5% |

主要结论：

- `LIQUIDITY` 是最重要的单一风格来源。
- `SIZE/BETA/RESVOL` 是次核心贡献因子。
- 风格合计贡献较高，但 residual 占比也非常大，不能只把策略理解为纯风格择时。

对应输出：

- `output/cne6/data/style_factor_attribution_summary_l20_s5_b2_e1_n100.csv`
- `output/cne6/images/style_factor_attribution_summary_l20_s5_b2_e1_n100.png`

## 6. 分时段归因

当前分段配置在脚本中维护：

```python
REGIMES = [
    ("steady_2020_to_2024_pre_jump", "2020-02-17", "2024-09-18"),
    ("jump_2024_q4", "2024-09-23", "2024-12-09"),
    ("jump_2025_mid", "2025-04-07", "2025-09-29"),
]
```

各阶段主要风格来源：

| 阶段 | 主要贡献因子 |
|---|---|
| 2020初至2024年9月 | LIQUIDITY、SIZE、RESVOL、RESMOM、MIDCAP |
| 2024年四季度高收益段 | BETA、TOPSI、STOM、EYIELD、LP |
| 2025年中高收益段 | BETA、SIZE、LIQUIDITY、MIDCAP、RESVOL |

解释：

- 平稳收益期主要由 `LIQUIDITY/SIZE/RESVOL/RESMOM` 支撑。
- 2024 年四季度的高收益并非完全由长期主因子驱动，`BETA/TOPSI/STOM` 更突出。
- 2025 年中段高收益重新回到 `BETA/SIZE/LIQUIDITY` 等核心因子。

对应输出：

- `output/cne6/data/style_factor_attribution_regime_summary_l20_s5_b2_e1_n100.csv`
- `output/cne6/images/style_factor_attribution_regime_summary_l20_s5_b2_e1_n100.png`

## 7. 风格择时有效性与持仓兑现

风格择时有效性表回答的是：

> 信号方向是否命中后续因子收益？实际持仓平均暴露是否兑现了信号方向？持仓平均暴露方向是否赚钱？

关键因子表现：

| 因子 | 信号命中率 | 信号-持仓一致率 | 持仓命中率 | 实际贡献 |
|---|---:|---:|---:|---:|
| LIQUIDITY | 86.4% | 87.4% | 77.7% | 45.9% |
| SIZE | 56.8% | 85.0% | 56.5% | 23.2% |
| BETA | 53.2% | 79.1% | 56.1% | 22.7% |
| RESVOL | 54.5% | 60.5% | 54.2% | 20.1% |
| TOPSI | 57.1% | 54.8% | 47.2% | -11.8% |
| STOQ | 56.5% | 58.8% | 46.5% | -9.3% |
| HISTVOL | 51.5% | 50.2% | 44.2% | -24.1% |

持仓内部暴露质量表进一步回答：

> 选出的 100 只股票内部，是多数股票一起押对方向，还是少数股票拉动组合平均暴露？

关键观察：

- `LIQUIDITY` 的方向正确股票占比高达 `70.9%`，但高暴露且方向正确只有 `4.1%`。这说明它是“广泛低强度命中”，不是少数高暴露股票驱动。
- `SIZE` 方向正确股票占比 `56.7%`，高暴露且方向正确 `12.6%`，持仓兑现较扎实。
- `CAPX/MIDCAP` 的高暴露且方向正确分别为 `17.3%/16.2%`，说明选股层面能选出较鲜明的风格股票。
- `TOPSI/STOQ/HISTVOL` 的高暴露且方向正确较低，且归因贡献为负，需要重点监控。

对应输出：

- `output/cne6/images/style_timing_effectiveness_table_l20_s5_b2_e1_n100.png`
- `output/cne6/images/style_holding_exposure_quality_table_l20_s5_b2_e1_n100.png`

## 8. 交易成本压力测试

当前测试口径：

```python
net_return = (1 - turnover * cost_rate) * (1 + gross_return) - 1
```

其中 `turnover` 为单边换手率，`cost_rate` 为单边交易成本。

| 单边成本 | 期末净值 | 年化收益 | 夏普 | 最大回撤 |
|---|---:|---:|---:|---:|
| 0bp | 8.01 | 42.7% | 1.38 | -18.0% |
| 5bp | 7.13 | 39.9% | 1.29 | -18.3% |
| 10bp | 6.35 | 37.2% | 1.19 | -18.6% |
| 20bp | 5.04 | 31.9% | 1.01 | -20.0% |
| 30bp | 3.99 | 26.7% | 0.83 | -21.5% |
| 50bp | 2.51 | 17.1% | 0.49 | -28.2% |
| 100bp | 0.78 | -4.1% | -0.25 | -55.8% |

结论：

- 在 `10bp-20bp` 单边成本下，策略仍然有较强收益。
- `50bp` 后收益质量明显恶化。
- `100bp` 下策略被交易成本打穿。
- 换手控制是后续优化优先级最高的问题之一。

对应输出：

- `output/cne6/data/transaction_cost_stress_summary_l20_s5_b2_e1_n100.csv`
- `output/cne6/images/transaction_cost_stress_l20_s5_b2_e1_n100.png`

## 9. 因子剔除/降权实验

实验目标：验证是否可以通过剔除或降权问题因子提升策略表现。

主实验在 `20bp` 成本后的净年化结果：

| 场景 | 20bp净年化 | 相对原始 | 平均换手 | 最大回撤 |
|---|---:|---:|---:|---:|
| 原始全部因子 | 31.9% | 0.0% | 76.9% | -18.0% |
| 核心加权，问题因子降权 | 30.5% | -1.3% | 75.1% | -18.9% |
| 问题因子降权 | 29.0% | -2.8% | 76.4% | -19.1% |
| 只保留核心和次级正贡献因子 | 28.9% | -2.9% | 74.3% | -20.3% |
| 剔除全样本负贡献因子 | 28.7% | -3.2% | 76.4% | -19.5% |
| 剔除 TOPSI/STOQ/HISTVOL | 28.2% | -3.6% | 76.9% | -20.1% |

单因子剔除留一法中，只有少数因子剔除后略有改善：

| 场景 | 20bp净年化 | 相对原始 | 最大回撤 |
|---|---:|---:|---:|
| 只剔除 EYIELD | 32.5% | +0.7% | -20.3% |
| 只剔除 LP | 32.5% | +0.7% | -20.3% |
| 只剔除 BLEV | 32.4% | +0.5% | -19.7% |
| 只剔除 STOM | 31.9% | +0.1% | -18.0% |

结论：

- 简单剔除 `TOPSI/STOQ/HISTVOL` 这类问题因子并没有提升策略。
- 全样本负贡献因子不等于应该剔除的因子。
- 因子通过余弦相似度共同决定股票集合，单个因子的负归因可能仍在选股结构中发挥筛选作用。
- 后续更值得做的是滚动可靠性加权，而不是静态样本内剔除。

对应输出：

- `output/cne6/data/factor_weight_experiment_summary_l20_s5_b2_e1_n100.csv`
- `output/cne6/images/factor_weight_experiment_l20_s5_b2_e1_n100.png`

## 10. Residual 归因

Residual 定义：

```text
Residual = 策略实际收益 - CNE6 风格因子解释收益
```

全样本 residual 拆解：

| 组件 | 累计贡献 | 策略算术收益占比 | 正贡献期占比 |
|---|---:|---:|---:|
| 风格因子解释部分 | 125.8% | 54.2% | 68.1% |
| Residual 合计 | 106.3% | 45.8% | 53.5% |
| 全市场等权共同项 | 94.8% | 40.9% | 54.2% |
| Residual 扣全市场后的选股残差 | 11.4% | 4.9% | 50.5% |
| 中证500共同项 | 45.6% | 19.7% | 50.2% |
| 中证1000共同项 | 47.7% | 20.6% | 51.2% |

核心结论：

- Residual 主要不是纯选股 alpha，而是接近全市场等权共同项。
- 中证500和中证1000只能解释 residual 的一部分，解释力低于全市场等权。
- 该现象与策略持仓偏小市值、高弹性股票的特征一致。

按信号日市场暴露分组：

| 分组维度 | 主要现象 |
|---|---|
| SIZE | Q1低暴露贡献 `38.6%`，占该维度 residual 的 `36.3%`，说明 residual 明显偏向低 SIZE，即偏小市值股票 |
| BETA | Q5高暴露贡献 `33.4%`，BETA 越高 residual 越高 |
| RESVOL | Q3-Q5 合计贡献较高，residual 偏向中高残差波动股票 |
| LIQUIDITY | Q4 贡献最高，低暴露和高暴露端也有贡献，不是简单单调关系 |

对应输出：

- `output/cne6/data/residual_attribution_summary_l20_s5_b2_e1_n100.csv`
- `output/cne6/data/residual_attribution_bucket_l20_s5_b2_e1_n100.csv`
- `output/cne6/images/residual_attribution_l20_s5_b2_e1_n100.png`

限制：

当前缓存没有行业分类字段，因此本版 residual 归因尚未拆分行业贡献。`src/models/barra_cne6.py` 中会读取行业分类，但目前没有把行业暴露或行业标签保存到 `output/cne6/data`。如需行业 residual 归因，建议新增行业缓存输出。

## 11. 风险与局限

### 11.1 高换手风险

平均单边换手为 `76.9%`，中位数为 `79.0%`。这会带来：

- 显著交易成本。
- 成交冲击风险。
- 对停牌、涨跌停、流动性的敏感性。
- 实盘容量约束。

### 11.2 Residual 来源不够纯

Residual 占策略收益 `45.8%`，但扣除全市场等权共同项后只剩 `4.9%`。这说明策略有很大一部分收益来自小票/全市场等权共同行情，而不完全是稳定选股 alpha。

### 11.3 年度稳定性

2024 年波动明显升高，年化波动约 `50.0%`，夏普仅 `0.39`。策略在某些市场状态下可能暴露出较强的高 beta、高波动或拥挤交易风险。

### 11.4 样本内因子实验的局限

因子剔除和降权实验均为样本内诊断，不能直接作为上线参数选择。尤其当因子共同决定股票集合时，单因子贡献和最终组合表现之间并非线性关系。

### 11.5 行业归因缺失

当前输出缺少行业标签，无法判断 residual 是否来自特定行业或主题。如果后续要做更接近 Barra 完整风险模型的归因，需要补充行业和国家因子维度。

## 12. 优化建议

### 12.1 优先做换手控制

建议方向：

- 加入持仓缓冲区：新股相似度必须显著高于老股才替换。
- 限制单期最大替换数量，例如每周最多替换 30-50 只。
- 在选股目标函数中加入换手惩罚。
- 对预期收益边际较弱的换仓动作不执行。

目标不是单纯降低换手，而是在 `20bp-50bp` 成本区间内提高净收益质量。

### 12.2 从静态因子剔除改为滚动可靠性加权

不建议直接剔除 `TOPSI/STOQ/HISTVOL`，因为样本内实验显示简单剔除会降低净年化。建议改为滚动权重：

```text
因子权重 = f(过去窗口信号命中率、持仓命中率、实际贡献、波动稳定性)
```

可测试窗口：

- 52周滚动可靠性
- 104周滚动可靠性
- 指数加权滚动可靠性

### 12.3 增加风险暴露约束

基于 residual 归因，建议监控或约束：

- `SIZE Q1` 小市值暴露
- `BETA Q5` 高 beta 暴露
- `RESVOL Q4/Q5` 高残差波动暴露
- 单期组合波动和回撤触发器

### 12.4 补充行业归因

建议将行业字段保存到输出目录，例如：

```text
output/cne6/data/industry_exposure_cne6.csv
```

或在 `factor_exposure_cne6.csv` 中追加 `sw_l1`。这样 residual 可以继续拆成：

```text
Residual = 市场共同项 + 行业项 + 风格遗漏项 + 个股特异项
```

### 12.5 做样本外和参数稳健性测试

建议测试：

- 不同 `long_prd/short_prd/channel_bins/extreme_value/top_n`
- 不同换仓频率
- 不同股票数量
- 不同市场阶段训练/验证切分
- 滚动 walk-forward 参数选择

## 13. 复现命令

主策略：

```powershell
python scripts\run_factor_timing_v3.py
```

完整风格归因：

```powershell
python scripts\run_style_factor_attribution_cne6.py
```

交易成本压力测试：

```powershell
python scripts\run_transaction_cost_stress_cne6.py
```

因子剔除/降权实验：

```powershell
python scripts\run_factor_weight_experiment_cne6.py
```

Residual 归因：

```powershell
python scripts\run_residual_attribution_cne6.py
```

## 14. 主要输出文件索引

| 文件 | 说明 |
|---|---|
| `output/cne6/data/portfolio_returns_l20_s5_b2_e1_n100.csv` | 策略周度收益与持仓 |
| `output/cne6/data/optimal_vectors_l20_s5_b2_e1_n100.csv` | 每期理想风格向量 |
| `output/cne6/data/style_factor_attribution_summary_l20_s5_b2_e1_n100.csv` | 全样本风格归因汇总 |
| `output/cne6/data/style_factor_attribution_regime_summary_l20_s5_b2_e1_n100.csv` | 分时段风格归因汇总 |
| `output/cne6/data/style_timing_effectiveness_summary_l20_s5_b2_e1_n100.csv` | 风格择时有效性汇总 |
| `output/cne6/data/style_holding_exposure_quality_summary_l20_s5_b2_e1_n100.csv` | 持仓内部暴露质量汇总 |
| `output/cne6/data/transaction_cost_stress_summary_l20_s5_b2_e1_n100.csv` | 交易成本压力测试汇总 |
| `output/cne6/data/factor_weight_experiment_summary_l20_s5_b2_e1_n100.csv` | 因子剔除/降权实验汇总 |
| `output/cne6/data/residual_attribution_summary_l20_s5_b2_e1_n100.csv` | Residual 主组件汇总 |
| `output/cne6/data/residual_attribution_bucket_l20_s5_b2_e1_n100.csv` | Residual 暴露分组汇总 |

## 15. 后续修订记录

| 日期 | 修改人 | 修改内容 |
|---|---|---|
| 2026-04-30 | Codex | 初版策略报告 |

## 16. 待补充问题

- 是否引入行业分类缓存并补充行业 residual 归因？
- 是否把交易成本测试扩展为双边成交额口径？
- 是否将换手缓冲机制写入策略主流程？
- 是否新增滚动可靠性加权策略版本？
- 是否做参数网格和 walk-forward 样本外测试？
