"""
生成 Barra CNE6 风格择时策略的 residual 归因。

输出：
1. 每期 residual 拆解明细
2. 逐股 residual 明细
3. 按暴露分组的 residual 汇总
4. residual 主要组件汇总
5. residual 归因图

说明：
当前缓存没有行业分类字段，因此本脚本先做可复现的 residual 拆解：
全市场等权共同项、指数共同项、逐股风格模型残差，以及按风格暴露分组的残差来源。
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis import residual_attribution as core


# 用这些信号日暴露维度给持仓股票分组，观察 residual 主要来自哪类股票。
BUCKET_FACTORS = ["SIZE", "LIQUIDITY", "BETA", "RESVOL"]


def main():
    """主流程：计算并保存 residual 归因。"""
    os.makedirs(core.DATA_DIR, exist_ok=True)
    os.makedirs(core.IMAGE_DIR, exist_ok=True)

    period_df, stock_df, bucket_summary_df, component_summary_df = core.run_residual_attribution(
        BUCKET_FACTORS
    )

    period_df.to_csv(core.RESIDUAL_ATTRIBUTION_PERIOD_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    stock_df.to_csv(core.RESIDUAL_ATTRIBUTION_STOCK_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    bucket_summary_df.to_csv(core.RESIDUAL_ATTRIBUTION_BUCKET_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    component_summary_df.to_csv(core.RESIDUAL_ATTRIBUTION_SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"Saved residual attribution period: {core.RESIDUAL_ATTRIBUTION_PERIOD_OUTPUT_PATH}")
    print(f"Saved residual attribution stock: {core.RESIDUAL_ATTRIBUTION_STOCK_OUTPUT_PATH}")
    print(f"Saved residual attribution bucket: {core.RESIDUAL_ATTRIBUTION_BUCKET_OUTPUT_PATH}")
    print(f"Saved residual attribution summary: {core.RESIDUAL_ATTRIBUTION_SUMMARY_OUTPUT_PATH}")
    print(f"Saved residual attribution plot: {core.RESIDUAL_ATTRIBUTION_PLOT_OUTPUT_PATH}")
    print(component_summary_df.to_string(index=False))
    print(bucket_summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
