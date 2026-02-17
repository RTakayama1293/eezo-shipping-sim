"""データ読み込み・販売価格検証モジュール."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def load_products() -> pd.DataFrame:
    """商品マスタを読み込む.

    Returns:
        商品マスタ DataFrame (金額列は int).
    """
    df = pd.read_csv(RAW_DIR / "products.csv")
    df = df.dropna(subset=["sku"])
    for col in ("cost_price", "selling_price", "weight_g"):
        df[col] = df[col].astype(int)
    df["market_reference_price"] = pd.to_numeric(
        df["market_reference_price"], errors="coerce"
    )
    return df


def load_shipping_rates() -> pd.DataFrame:
    """配送料金テーブルを読み込む.

    Returns:
        配送料金 DataFrame (各サイズ列は int).
    """
    df = pd.read_csv(RAW_DIR / "shipping_rates.csv")
    for col in ("size_60", "size_80", "size_100", "size_120", "cool_surcharge"):
        df[col] = df[col].astype(int)
    return df


def load_config() -> dict[str, Any]:
    """シミュレーション設定を読み込む.

    Returns:
        config 辞書.
    """
    with open(RAW_DIR / "config.json", encoding="utf-8") as f:
        return json.load(f)


def load_scenarios() -> pd.DataFrame:
    """シナリオ一覧を読み込む.

    Returns:
        シナリオ DataFrame.
    """
    df = pd.read_csv(RAW_DIR / "scenarios.csv")
    return df


def validate_selling_prices(
    products: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    """販売価格の妥当性を検証する.

    検証項目:
      1. 販売価格 >= 仕入原価 / (1 - margin_rate) + shipping_buffer
      2. 市場参考価格がある場合、プレミアム率が上限以内か

    Args:
        products: 商品マスタ DataFrame.
        config: シミュレーション設定辞書.

    Returns:
        検証結果を列追加した DataFrame.
    """
    margin_rate = config["layer1_markup"]["base_margin_rate"]
    buffer = config["layer1_markup"]["shipping_buffer_per_item"]
    max_premium = config["constraints"]["max_market_premium_rate"]

    df = products.copy()

    # 理論最低販売価格
    df["theoretical_min_price"] = (
        (df["cost_price"] / (1 - margin_rate)).apply(lambda x: int(x)) + buffer
    )
    df["price_ok"] = df["selling_price"] >= df["theoretical_min_price"]

    # 市場価格プレミアム率
    has_market = df["market_reference_price"].notna()
    df.loc[has_market, "market_premium_rate"] = (
        (df.loc[has_market, "selling_price"] - df.loc[has_market, "market_reference_price"])
        / df.loc[has_market, "market_reference_price"]
    )
    df.loc[~has_market, "market_premium_rate"] = None
    df["market_premium_ok"] = True
    df.loc[has_market, "market_premium_ok"] = (
        df.loc[has_market, "market_premium_rate"] <= max_premium
    )

    return df
