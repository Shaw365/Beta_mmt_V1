# 输出文件说明

本文件夹包含 Barra CNE5 和 CNE6 模型的所有输出文件，按照模型和文件类型进行分类存储。

## 目录结构

```
output/
├── cne5/                      # Barra CNE5 模型输出
│   ├── data/                  # 数据文件
│   │   ├── factor_returns_cne5.csv           # 因子收益率数据
│   │   └── cumulative_returns_cne5.csv       # 累计收益率数据
│   └── images/                # 图像文件
│       └── cumulative_returns_cne5.png       # 累计收益率图
│
└── cne6/                      # Barra CNE6 模型输出
    ├── data/                  # 数据文件
    │   ├── factor_returns_cne6.csv           # 因子收益率数据
    │   └── cumulative_returns_cne6.csv       # 累计收益率数据
    └── images/                # 图像文件
        └── cumulative_returns_cne6.png       # 累计收益率图
```

## 文件命名规则

- 所有输出文件都带有 `_cne5` 或 `_cne6` 后缀，以区分不同模型的输出
- 数据文件存储在 `data/` 子文件夹中
- 图像文件存储在 `images/` 子文件夹中

## 文件说明

### CNE5 模型输出

#### 数据文件
- `factor_returns_cne5.csv`: 包含 10 个风格因子的日收益率数据
  - SIZE: 规模因子
  - BETA: 贝塔因子
  - MOMENTUM: 动量因子
  - RESVOL: 残差波动率因子
  - NLSIZE: 非线性规模因子
  - BTOP: 账面市值比因子
  - LIQUIDITY: 流动性因子
  - EYIELD: 盈利收益率因子
  - GROWTH: 成长因子
  - LEVERAGE: 杠杆因子

- `cumulative_returns_cne5.csv`: 各因子的累计收益率序列

#### 图像文件
- `cumulative_returns_cne5.png`: 10 个风格因子的累计收益率曲线图

### CNE6 模型输出

#### 数据文件
- `factor_returns_cne6.csv`: 包含 25 个风格因子的日收益率数据
  - 规模因子: SIZE, MIDCAP
  - 波动率因子: BETA, RESVOL, HISTVOL
  - 动量因子: MOMENTUM, RESMOM
  - 价值因子: BTOP, EYIELD, CFP, SP, LP
  - 成长因子: EGRO, SGRO
  - 杠杆因子: MLEV, BLEV
  - 流动性因子: LIQUIDITY, STOM, STOQ
  - 盈利质量因子: ROE, ROA
  - 投资因子: CAPX, AGRO
  - 其他因子: TOPSI, SEASON

- `cumulative_returns_cne6.csv`: 各因子的累计收益率序列

#### 图像文件
- `cumulative_returns_cne6.png`: 25 个风格因子的累计收益率曲线图

## 使用方法

运行相应的模型脚本即可自动生成输出文件：

```bash
# 运行 CNE5 模型
python barra_cne5.py

# 运行 CNE6 模型
python barra_cne6.py
```

输出文件将自动保存到对应的文件夹中。
