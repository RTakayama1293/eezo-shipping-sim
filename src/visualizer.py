"""可視化モジュール."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd


def _setup_font() -> None:
    """日本語フォントを設定する."""
    jp_fonts = [
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in jp_fonts:
        if Path(fp).exists():
            fm.fontManager.addfont(fp)
            prop = fm.FontProperties(fname=fp)
            plt.rcParams["font.family"] = prop.get_name()
            return
    # フォールバック: sans-serif
    plt.rcParams["font.family"] = "sans-serif"


_setup_font()
plt.rcParams["axes.unicode_minus"] = False


def plot_margin_bar(
    df: pd.DataFrame,
    output_path: Path,
    min_margin: float = 0.15,
) -> None:
    """シナリオ別粗利率の棒グラフを描画する.

    Args:
        df: シミュレーション結果 DataFrame.
        output_path: 出力ファイルパス.
        min_margin: 最低粗利率ライン.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    colors = ["#2ecc71" if ok else "#e74c3c" for ok in df["margin_ok"]]
    bars = ax.bar(range(len(df)), df["margin_rate"] * 100, color=colors, edgecolor="white")

    ax.axhline(y=min_margin * 100, color="#e67e22", linestyle="--", linewidth=2, label=f"Min Margin {min_margin*100:.0f}%")

    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(
        [f"{sid}\n{sname}" for sid, sname in zip(df["scenario_id"], df["scenario_name"])],
        rotation=45, ha="right", fontsize=9,
    )
    ax.set_ylabel("Gross Margin Rate (%)", fontsize=12)
    ax.set_title("Scenario Margin Analysis", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)

    for bar, rate in zip(bars, df["margin_rate"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{rate*100:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_ylim(0, max(df["margin_rate"] * 100) * 1.2)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_profit_breakdown(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """シナリオ別収支内訳のスタック棒グラフを描画する.

    Args:
        df: シミュレーション結果 DataFrame.
        output_path: 出力ファイルパス.
    """
    fig, ax = plt.subplots(figsize=(14, 7))

    x = np.arange(len(df))
    width = 0.35

    # 収入側 (積み上げ)
    ax.bar(x - width / 2, df["total_selling_price"], width, label="Selling Price", color="#3498db")
    ax.bar(x - width / 2, df["fixed_shipping"], width, bottom=df["total_selling_price"],
           label="Fixed Shipping (1,000)", color="#2ecc71")

    # 支出側 (積み上げ)
    ax.bar(x + width / 2, df["total_cost_price"], width, label="Cost Price", color="#e74c3c")
    ax.bar(x + width / 2, df["actual_shipping_cost"], width, bottom=df["total_cost_price"],
           label="Actual Shipping", color="#e67e22")
    ax.bar(x + width / 2, df["discount"], width,
           bottom=df["total_cost_price"] + df["actual_shipping_cost"],
           label="Discount", color="#9b59b6")

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{sid}\n{sname}" for sid, sname in zip(df["scenario_id"], df["scenario_name"])],
        rotation=45, ha="right", fontsize=9,
    )
    ax.set_ylabel("Amount (JPY)", fontsize=12)
    ax.set_title("Revenue vs Cost Breakdown by Scenario", fontsize=14, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left")
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_sensitivity(
    sens_df: pd.DataFrame,
    param_label: str,
    output_path: Path,
    min_margin: float = 0.15,
) -> None:
    """感度分析グラフを描画する.

    Args:
        sens_df: 感度分析結果 DataFrame.
        param_label: パラメータの表示名.
        output_path: 出力ファイルパス.
        min_margin: 最低粗利率ライン.
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    scenarios = sens_df["scenario_id"].unique()
    cmap = plt.cm.get_cmap("tab10", len(scenarios))

    for i, sid in enumerate(scenarios):
        subset = sens_df[sens_df["scenario_id"] == sid]
        sname = subset["scenario_name"].iloc[0]
        ax.plot(
            subset["param_value"], subset["margin_rate"] * 100,
            marker="o", label=f"{sid} {sname}", color=cmap(i), linewidth=2,
        )

    ax.axhline(y=min_margin * 100, color="#e74c3c", linestyle="--", linewidth=2,
               label=f"Min Margin {min_margin*100:.0f}%")

    ax.set_xlabel(param_label, fontsize=12)
    ax.set_ylabel("Gross Margin Rate (%)", fontsize=12)
    ax.set_title(f"Sensitivity Analysis: {param_label}", fontsize=14, fontweight="bold")
    ax.legend(fontsize=8, loc="best", ncol=2)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_price_validation(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """販売価格検証の散布図を描画する.

    Args:
        df: 検証済み商品マスタ.
        output_path: 出力ファイルパス.
    """
    has_market = df["market_reference_price"].notna()
    subset = df[has_market].copy()

    if subset.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    colors = ["#2ecc71" if ok else "#e74c3c" for ok in subset["market_premium_ok"]]
    ax.scatter(subset["market_reference_price"], subset["selling_price"],
               c=colors, s=80, edgecolors="white", linewidth=0.5, zorder=3)

    # 対角線 (selling = market)
    max_val = max(subset["market_reference_price"].max(), subset["selling_price"].max()) * 1.1
    ax.plot([0, max_val], [0, max_val], "k--", alpha=0.3, label="Market = Selling")
    ax.plot([0, max_val], [0, max_val * 1.15], "r--", alpha=0.3, label="+15% Premium Line")

    for _, row in subset.iterrows():
        ax.annotate(
            str(row["sku"])[-8:],
            (row["market_reference_price"], row["selling_price"]),
            fontsize=6, alpha=0.7,
            xytext=(3, 3), textcoords="offset points",
        )

    ax.set_xlabel("Market Reference Price (JPY)", fontsize=12)
    ax.set_ylabel("Selling Price (JPY)", fontsize=12)
    ax.set_title("Selling Price vs Market Reference", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
