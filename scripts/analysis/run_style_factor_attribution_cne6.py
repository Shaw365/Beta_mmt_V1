"""
生成 Barra CNE6 风格归因全套报告。

这是总入口脚本，会一次性生成：
1. 全样本风格收益归因
2. 分时段风格收益归因
3. 风格择时有效性分析

核心计算逻辑位于 src.analysis.style_factor_attribution。
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import style_factor_attribution


# 分时段设置：
# 这里按策略净值曲线的形态拆成“平稳收益期 + 两段跃迁期”。
# 如果想测试其他口径，只需要改这里的起止日期后重新运行脚本。
REGIMES = [
    ("steady_2020_to_2024_pre_jump", "2020-02-17", "2024-09-18"),
    ("jump_2024_q4", "2024-09-23", "2024-12-09"),
    ("jump_2025_mid", "2025-04-07", "2025-09-29"),
]


if __name__ == "__main__":
    style_factor_attribution.main(REGIMES)
