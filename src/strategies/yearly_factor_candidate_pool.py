"""
Yearly factor candidate pool for the Barra timing strategy.

The pool is built before Barra stock selection:
1. Pick the factor set by apply_year, where apply_year = selection_year + 1.
2. On each signal date, rank stocks cross-sectionally for every selected factor.
3. Flip factors whose historical Rank IC is negative.
4. Equal-weight the signed ranks and keep the top N stocks.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


class YearlyFactorCandidatePool:
    """Build weekly candidate pools from yearly selected factor combinations."""

    def __init__(
        self,
        selected_factors_path: str | Path,
        factor_root: str | Path,
        pool_size: int = 500,
        min_factor_fraction: float = 0.2,
        min_factor_count: int = 3,
        cache_dir: str | Path | None = None,
        market_filter_df: pd.DataFrame | None = None,
        min_float_cap_quantile: float = 0.0,
        min_amount_quantile: float = 0.0,
    ) -> None:
        self.selected_factors_path = Path(selected_factors_path)
        self.factor_root = Path(factor_root)
        self.pool_size = int(pool_size)
        self.min_factor_fraction = float(min_factor_fraction)
        self.min_factor_count = int(min_factor_count)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.min_float_cap_quantile = float(min_float_cap_quantile)
        self.min_amount_quantile = float(min_amount_quantile)

        self.selected_factors = pd.read_csv(self.selected_factors_path)
        self.selected_factors["apply_year"] = self.selected_factors["apply_year"].astype(int)
        self.selected_factors["rank_ic_mean"] = pd.to_numeric(
            self.selected_factors["rank_ic_mean"], errors="coerce"
        )
        self._year_factor_data: dict[int, pd.DataFrame] = {}
        self._pool_lookup: dict[pd.Timestamp, list[str]] = {}
        self._pool_summary_rows: list[dict] = []
        self.market_filter_df = self._prepare_market_filter_df(market_filter_df)
        self._market_dates = (
            pd.Index(sorted(self.market_filter_df["date"].unique()))
            if self.market_filter_df is not None and not self.market_filter_df.empty
            else pd.Index([])
        )

    def _prepare_market_filter_df(self, market_filter_df: pd.DataFrame | None) -> pd.DataFrame | None:
        if market_filter_df is None:
            return None
        required = {"date", "code"}
        if not required.issubset(market_filter_df.columns):
            raise ValueError("market_filter_df must contain date and code columns")
        cols = ["date", "code"]
        for col in ("float_cap", "amount"):
            if col in market_filter_df.columns:
                cols.append(col)
        data = market_filter_df[cols].copy()
        data["date"] = pd.to_datetime(data["date"])
        data["code"] = data["code"].astype(str)
        for col in ("float_cap", "amount"):
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")
        return data

    def _cache_suffix(self) -> str:
        parts = []
        if self.min_float_cap_quantile > 0:
            parts.append(f"fcapq{int(round(self.min_float_cap_quantile * 100))}")
        if self.min_amount_quantile > 0:
            parts.append(f"amtq{int(round(self.min_amount_quantile * 100))}")
        return "" if not parts else "_" + "_".join(parts)

    def _market_filter_for_date(self, signal_date: pd.Timestamp) -> tuple[pd.DataFrame | None, pd.Timestamp | None]:
        if self.market_filter_df is None or self._market_dates.empty:
            return None, None
        pos = self._market_dates.searchsorted(np.datetime64(signal_date), side="right") - 1
        if pos < 0:
            return None, None
        market_date = pd.Timestamp(self._market_dates[pos])
        return self.market_filter_df[self.market_filter_df["date"] == market_date].copy(), market_date

    def _apply_market_filters(
        self,
        scored: pd.DataFrame,
        signal_date: pd.Timestamp,
    ) -> tuple[pd.DataFrame, dict]:
        info = {
            "pre_market_filter_count": int(len(scored)),
            "post_market_filter_count": int(len(scored)),
            "market_filter_date": pd.NaT,
            "float_cap_threshold": np.nan,
            "amount_threshold": np.nan,
        }
        if self.min_float_cap_quantile <= 0 and self.min_amount_quantile <= 0:
            return scored, info

        market, market_date = self._market_filter_for_date(signal_date)
        if market is None or market.empty:
            print(f"  警告: {signal_date.date()} 无市值/成交额过滤数据，沿用未过滤候选池")
            return scored, info

        filtered = scored.merge(market, on="code", how="left")
        info["market_filter_date"] = market_date

        if self.min_float_cap_quantile > 0:
            if "float_cap" not in filtered.columns:
                raise ValueError("min_float_cap_quantile requires market_filter_df.float_cap")
            threshold = filtered["float_cap"].quantile(self.min_float_cap_quantile)
            info["float_cap_threshold"] = float(threshold) if pd.notna(threshold) else np.nan
            filtered = filtered[filtered["float_cap"].notna() & (filtered["float_cap"] >= threshold)]

        if self.min_amount_quantile > 0:
            if "amount" not in filtered.columns:
                raise ValueError("min_amount_quantile requires market_filter_df.amount")
            threshold = filtered["amount"].quantile(self.min_amount_quantile)
            info["amount_threshold"] = float(threshold) if pd.notna(threshold) else np.nan
            filtered = filtered[filtered["amount"].notna() & (filtered["amount"] >= threshold)]

        info["post_market_filter_count"] = int(len(filtered))
        return filtered, info

    def _resolve_factor_file(self, row: pd.Series) -> Path:
        if "file" in row and pd.notna(row["file"]):
            path = Path(str(row["file"]))
            if path.is_absolute():
                return path
            direct = self.factor_root.parent / path
            if direct.exists():
                return direct
        return self.factor_root / str(row["file_name"])

    def _load_apply_year_data(self, apply_year: int) -> pd.DataFrame:
        if apply_year in self._year_factor_data:
            return self._year_factor_data[apply_year]

        factors = self.selected_factors[self.selected_factors["apply_year"] == apply_year].copy()
        if factors.empty:
            self._year_factor_data[apply_year] = pd.DataFrame(columns=["date", "code"])
            return self._year_factor_data[apply_year]

        wide = None
        used_names: list[str] = []
        for _, row in factors.iterrows():
            factor_name = str(row["factor"])
            factor_col = str(row["source_factor_col"])
            path = self._resolve_factor_file(row)
            if not path.exists():
                print(f"  警告: 因子文件不存在，跳过 {factor_name}: {path}")
                continue

            data = pd.read_csv(path, usecols=["date", "code", factor_col])
            data["date"] = pd.to_datetime(data["date"])
            data = data[data["date"].dt.year == apply_year]
            if data.empty:
                continue
            data["code"] = data["code"].astype(str)
            data[factor_name] = pd.to_numeric(data[factor_col], errors="coerce")
            data = data[["date", "code", factor_name]]

            if wide is None:
                wide = data
            else:
                wide = wide.merge(data, on=["date", "code"], how="outer")
            used_names.append(factor_name)

        if wide is None:
            wide = pd.DataFrame(columns=["date", "code"])
        else:
            wide = wide.sort_values(["date", "code"]).reset_index(drop=True)

        self._year_factor_data[apply_year] = wide
        print(
            f"  已加载 {apply_year} 年候选池因子: {len(used_names)} 个, "
            f"{wide['date'].nunique() if 'date' in wide else 0} 个交易日"
        )
        return wide

    def score_candidates(self, signal_date: pd.Timestamp, candidate_codes: list[str]) -> pd.DataFrame:
        """Score a supplied Barra candidate list with the yearly Alpha factor set."""
        signal_date = pd.Timestamp(signal_date)
        candidate_codes = list(dict.fromkeys(str(code) for code in candidate_codes))
        if len(candidate_codes) == 0:
            return pd.DataFrame(columns=["code", "score", "valid_factor_count", "factor_data_date"])

        apply_year = signal_date.year
        factor_data = self._load_apply_year_data(apply_year)
        if factor_data.empty:
            return pd.DataFrame(columns=["code", "score", "valid_factor_count", "factor_data_date"])

        selected = self.selected_factors[self.selected_factors["apply_year"] == apply_year].copy()
        factor_cols = [f for f in selected["factor"].astype(str).tolist() if f in factor_data.columns]
        if len(factor_cols) == 0:
            return pd.DataFrame(columns=["code", "score", "valid_factor_count", "factor_data_date"])

        signs = selected.set_index("factor")["rank_ic_mean"].apply(
            lambda x: 1.0 if x >= 0 else -1.0
        ).to_dict()
        min_required = max(self.min_factor_count, int(np.ceil(len(factor_cols) * self.min_factor_fraction)))

        available_dates = pd.Index(sorted(factor_data["date"].unique()))
        pos = available_dates.searchsorted(np.datetime64(signal_date), side="right") - 1
        if pos < 0:
            return pd.DataFrame(columns=["code", "score", "valid_factor_count", "factor_data_date"])

        data_date = pd.Timestamp(available_dates[pos])
        current = factor_data[
            (factor_data["date"] == data_date) & (factor_data["code"].astype(str).isin(candidate_codes))
        ].copy()
        if current.empty:
            return pd.DataFrame(columns=["code", "score", "valid_factor_count", "factor_data_date"])

        score_parts = []
        for factor in factor_cols:
            values = pd.to_numeric(current[factor], errors="coerce")
            if values.notna().sum() < min(30, len(current)):
                continue
            ranks = values.rank(pct=True, method="average")
            score_parts.append(ranks * signs.get(factor, 1.0))

        if len(score_parts) < min_required:
            print(
                f"  Warning: {signal_date.date()} has {len(score_parts)} usable Alpha factors, "
                f"below required {min_required}; skip Alpha second-stage selection"
            )
            return pd.DataFrame(columns=["code", "score", "valid_factor_count", "factor_data_date"])

        score_frame = pd.concat(score_parts, axis=1)
        scored = (
            pd.DataFrame(
                {
                    "code": current["code"].astype(str).values,
                    "score": score_frame.mean(axis=1, skipna=True).values,
                    "valid_factor_count": score_frame.notna().sum(axis=1).values,
                    "factor_data_date": data_date,
                }
            )
            .dropna(subset=["score"])
            .query("valid_factor_count >= @min_required")
        )
        scored, _ = self._apply_market_filters(scored, signal_date)

        return scored.sort_values(["score", "code"], ascending=[False, True]).reset_index(drop=True)

    def select_stocks(self, date: pd.Timestamp, candidate_codes: list[str], top_n: int = 100) -> list[str]:
        """Select Top N names from a supplied Barra pool using yearly Alpha factors."""
        scores = self.score_candidates(date, candidate_codes)
        if len(scores) == 0:
            return []
        return scores.head(int(top_n))["code"].astype(str).tolist()

    def build_for_dates(self, signal_dates: list[pd.Timestamp]) -> None:
        """Precompute candidate pool lookup for the supplied signal dates."""
        if len(signal_dates) == 0:
            return

        signal_dates = sorted(pd.to_datetime(signal_dates))
        for apply_year in sorted({d.year for d in signal_dates}):
            year_dates = [d for d in signal_dates if d.year == apply_year]
            self._build_for_apply_year(apply_year, year_dates)

    def _build_for_apply_year(self, apply_year: int, signal_dates: list[pd.Timestamp]) -> None:
        cache_path = None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self.cache_dir / (
                f"yearly_factor_candidate_pool_{apply_year}_top{self.pool_size}{self._cache_suffix()}.csv"
            )
            if cache_path.exists():
                cached = pd.read_csv(cache_path)
                cached["signal_date"] = pd.to_datetime(cached["signal_date"])
                wanted = set(signal_dates)
                for date, group in cached[cached["signal_date"].isin(wanted)].groupby("signal_date"):
                    group = group.sort_values("rank")
                    self._pool_lookup[pd.Timestamp(date)] = group["code"].astype(str).tolist()
                    selected = self.selected_factors[self.selected_factors["apply_year"] == apply_year]
                    min_required = max(
                        self.min_factor_count,
                        int(np.ceil(len(selected) * self.min_factor_fraction)),
                    )
                    self._pool_summary_rows.append(
                        {
                            "signal_date": pd.Timestamp(date),
                            "apply_year": apply_year,
                            "factor_data_date": pd.to_datetime(group["factor_data_date"].iloc[0]),
                            "num_factors": int(len(selected)),
                            "used_factors": int(group["valid_factor_count"].max()),
                            "pool_size": int(len(group)),
                            "min_required_factors": min_required,
                            "pre_market_filter_count": int(group["pre_market_filter_count"].iloc[0])
                            if "pre_market_filter_count" in group.columns
                            else np.nan,
                            "post_market_filter_count": int(group["post_market_filter_count"].iloc[0])
                            if "post_market_filter_count" in group.columns
                            else np.nan,
                            "market_filter_date": pd.to_datetime(group["market_filter_date"].iloc[0])
                            if "market_filter_date" in group.columns
                            else pd.NaT,
                            "float_cap_threshold": float(group["float_cap_threshold"].iloc[0])
                            if "float_cap_threshold" in group.columns
                            else np.nan,
                            "amount_threshold": float(group["amount_threshold"].iloc[0])
                            if "amount_threshold" in group.columns
                            else np.nan,
                        }
                    )
                if wanted.issubset(set(self._pool_lookup.keys())):
                    print(f"  使用候选池缓存: {cache_path}")
                    return

        factor_data = self._load_apply_year_data(apply_year)
        if factor_data.empty:
            return

        selected = self.selected_factors[self.selected_factors["apply_year"] == apply_year].copy()
        factor_cols = [f for f in selected["factor"].astype(str).tolist() if f in factor_data.columns]
        signs = selected.set_index("factor")["rank_ic_mean"].apply(lambda x: 1.0 if x >= 0 else -1.0).to_dict()
        min_required = max(self.min_factor_count, int(np.ceil(len(factor_cols) * self.min_factor_fraction)))

        rows = []
        available_dates = pd.Index(sorted(factor_data["date"].unique()))
        for signal_date in signal_dates:
            pos = available_dates.searchsorted(np.datetime64(signal_date), side="right") - 1
            if pos < 0:
                continue
            data_date = pd.Timestamp(available_dates[pos])
            current = factor_data[factor_data["date"] == data_date].copy()
            if current.empty:
                continue

            score_parts = []
            for factor in factor_cols:
                values = pd.to_numeric(current[factor], errors="coerce")
                if values.notna().sum() < 30:
                    continue
                ranks = values.rank(pct=True, method="average")
                score_parts.append(ranks * signs.get(factor, 1.0))

            if len(score_parts) < min_required:
                print(
                    f"  警告: {signal_date.date()} 可用候选池因子 {len(score_parts)} 个，"
                    f"低于要求 {min_required}，跳过"
                )
                continue

            score = pd.concat(score_parts, axis=1).mean(axis=1, skipna=True)
            valid_count = pd.concat(score_parts, axis=1).notna().sum(axis=1)
            scored = (
                pd.DataFrame(
                    {
                        "code": current["code"].astype(str).values,
                        "score": score.values,
                        "valid_factor_count": valid_count.values,
                    }
                )
                .dropna(subset=["score"])
                .query("valid_factor_count >= @min_required")
            )
            scored, market_filter_info = self._apply_market_filters(scored, signal_date)
            ranked = (
                scored
                .sort_values(["score", "code"], ascending=[False, True])
                .head(self.pool_size)
            )

            codes = ranked["code"].tolist()
            self._pool_lookup[pd.Timestamp(signal_date)] = codes
            self._pool_summary_rows.append(
                {
                    "signal_date": signal_date,
                    "apply_year": apply_year,
                    "factor_data_date": data_date,
                    "num_factors": len(factor_cols),
                    "used_factors": len(score_parts),
                    "pool_size": len(codes),
                    "min_required_factors": min_required,
                    **market_filter_info,
                }
            )
            for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
                rows.append(
                    {
                        "signal_date": signal_date,
                        "factor_data_date": data_date,
                        "rank": rank,
                        "code": row["code"],
                        "score": row["score"],
                        "valid_factor_count": int(row["valid_factor_count"]),
                        "pre_market_filter_count": market_filter_info["pre_market_filter_count"],
                        "post_market_filter_count": market_filter_info["post_market_filter_count"],
                        "market_filter_date": market_filter_info["market_filter_date"],
                        "float_cap_threshold": market_filter_info["float_cap_threshold"],
                        "amount_threshold": market_filter_info["amount_threshold"],
                    }
                )

        if cache_path is not None and rows:
            pd.DataFrame(rows).to_csv(cache_path, index=False, encoding="utf-8-sig")

    def get_pool(self, signal_date: pd.Timestamp) -> list[str]:
        return self._pool_lookup.get(pd.Timestamp(signal_date), [])

    def summary(self) -> pd.DataFrame:
        if not self._pool_summary_rows:
            return pd.DataFrame()
        return pd.DataFrame(self._pool_summary_rows)
