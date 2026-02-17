"""粗利計算・シミュレーションエンジン."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ShipmentGroup:
    """同一仕入先・同一温度帯の出荷グループ."""

    supplier: str
    temp_zone: str
    skus: list[str] = field(default_factory=list)
    total_weight_g: int = 0
    total_cost: int = 0
    total_selling: int = 0
    item_count: int = 0


@dataclass
class ScenarioResult:
    """シナリオ別シミュレーション結果."""

    scenario_id: str
    scenario_name: str
    region: str
    items: list[str]
    total_selling_price: int = 0
    total_cost_price: int = 0
    fixed_shipping_revenue: int = 0
    actual_shipping_cost: int = 0
    discount_amount: int = 0
    shipment_count: int = 0
    gross_profit: int = 0
    margin_rate: float = 0.0
    margin_ok: bool = False
    shipment_groups: list[ShipmentGroup] = field(default_factory=list)


def determine_size_code(total_weight_g: int) -> str:
    """重量からサイズ区分を判定する.

    Args:
        total_weight_g: 合計重量(g).

    Returns:
        サイズ区分 (size_60 / size_80 / size_100 / size_120).
    """
    if total_weight_g <= 2000:
        return "size_60"
    elif total_weight_g <= 5000:
        return "size_80"
    elif total_weight_g <= 10000:
        return "size_100"
    else:
        return "size_120"


def calc_shipping_cost(
    weight_g: int,
    region: str,
    temp_zone: str,
    shipping_rates: pd.DataFrame,
) -> int:
    """実配送コストを算出する.

    Args:
        weight_g: 出荷グループの合計重量(g).
        region: 配送先地域.
        temp_zone: 温度帯.
        shipping_rates: 配送料金テーブル.

    Returns:
        配送コスト (円, int).
    """
    size_col = determine_size_code(weight_g)
    row = shipping_rates[shipping_rates["region"] == region].iloc[0]
    base = int(row[size_col])
    surcharge = int(row["cool_surcharge"]) if temp_zone in ("frozen", "chilled") else 0
    return base + surcharge


def calc_discount(
    item_count: int,
    same_supplier: bool,
    config: dict[str, Any],
) -> int:
    """合わせ買いディスカウント額を計算する.

    Args:
        item_count: 同一仕入先の商品数.
        same_supplier: 同一仕入先かどうか.
        config: 設定辞書.

    Returns:
        ディスカウント額 (円, int).
    """
    if not same_supplier or item_count < 2:
        return 0

    tiers = config["layer3_discount"]["tiers"]
    discount = 0
    for tier in tiers:
        if item_count >= tier["min_items"]:
            discount = int(tier["discount_amount"])
    return discount


def build_shipment_groups(
    item_skus: list[str],
    products: pd.DataFrame,
) -> list[ShipmentGroup]:
    """カート内商品を出荷グループに分割する.

    同一仕入先かつ同一温度帯は同梱（1つの出荷グループ）。
    異なる仕入先・異なる温度帯は別出荷。

    Args:
        item_skus: カート内のSKUリスト.
        products: 商品マスタ.

    Returns:
        出荷グループのリスト.
    """
    groups: dict[tuple[str, str], ShipmentGroup] = {}

    for sku in item_skus:
        prod = products[products["sku"] == sku]
        if prod.empty:
            continue
        p = prod.iloc[0]
        supplier = str(p["supplier"])
        temp_zone = str(p["temp_zone"])
        key = (supplier, temp_zone)

        if key not in groups:
            groups[key] = ShipmentGroup(supplier=supplier, temp_zone=temp_zone)

        g = groups[key]
        g.skus.append(sku)
        g.total_weight_g += int(p["weight_g"])
        g.total_cost += int(p["cost_price"])
        g.total_selling += int(p["selling_price"])
        g.item_count += 1

    return list(groups.values())


def simulate_scenario(
    scenario: pd.Series,
    products: pd.DataFrame,
    shipping_rates: pd.DataFrame,
    config: dict[str, Any],
) -> ScenarioResult:
    """1シナリオの損益をシミュレーションする.

    Args:
        scenario: シナリオ行.
        products: 商品マスタ.
        shipping_rates: 配送料金テーブル.
        config: 設定辞書.

    Returns:
        シナリオ別シミュレーション結果.
    """
    item_skus = str(scenario["items"]).split(";")
    region = str(scenario["region"])

    groups = build_shipment_groups(item_skus, products)

    total_selling = sum(g.total_selling for g in groups)
    total_cost = sum(g.total_cost for g in groups)
    fixed_shipping = int(config["layer2_fixed_shipping"]["display_amount"])

    # 実配送コスト: 各出荷グループごとに計算
    actual_shipping = 0
    for g in groups:
        actual_shipping += calc_shipping_cost(
            g.total_weight_g, region, g.temp_zone, shipping_rates
        )

    # ディスカウント: 同一仕入先のグループ内アイテム数で判定
    # Shopifyは1注文に1つの自動ディスカウントのみ → 最大の割引を適用
    discount = 0
    supplier_item_counts: dict[str, int] = {}
    for g in groups:
        supplier_item_counts[g.supplier] = (
            supplier_item_counts.get(g.supplier, 0) + g.item_count
        )
    for supplier, count in supplier_item_counts.items():
        d = calc_discount(count, same_supplier=True, config=config)
        if d > discount:
            discount = d

    # 粗利計算
    # 顧客支払額 = 商品合計 + 固定送料 - ディスカウント
    customer_payment = total_selling + fixed_shipping - discount
    # 粗利 = 顧客支払額 - 仕入原価 - 実配送コスト
    gross_profit = customer_payment - total_cost - actual_shipping
    # 粗利率 = 粗利 / 顧客支払額
    margin_rate = gross_profit / customer_payment if customer_payment > 0 else 0.0

    min_margin = config["constraints"]["min_margin_rate"]

    return ScenarioResult(
        scenario_id=str(scenario["scenario_id"]),
        scenario_name=str(scenario["scenario_name"]),
        region=region,
        items=item_skus,
        total_selling_price=total_selling,
        total_cost_price=total_cost,
        fixed_shipping_revenue=fixed_shipping,
        actual_shipping_cost=actual_shipping,
        discount_amount=discount,
        shipment_count=len(groups),
        gross_profit=gross_profit,
        margin_rate=round(margin_rate, 4),
        margin_ok=margin_rate >= min_margin,
        shipment_groups=groups,
    )


def run_all_scenarios(
    scenarios: pd.DataFrame,
    products: pd.DataFrame,
    shipping_rates: pd.DataFrame,
    config: dict[str, Any],
) -> list[ScenarioResult]:
    """全シナリオのシミュレーションを実行する.

    Args:
        scenarios: シナリオ一覧 DataFrame.
        products: 商品マスタ.
        shipping_rates: 配送料金テーブル.
        config: 設定辞書.

    Returns:
        全シナリオの結果リスト.
    """
    results = []
    for _, row in scenarios.iterrows():
        result = simulate_scenario(row, products, shipping_rates, config)
        results.append(result)
    return results


def results_to_dataframe(results: list[ScenarioResult]) -> pd.DataFrame:
    """シミュレーション結果をDataFrameに変換する.

    Args:
        results: ScenarioResultのリスト.

    Returns:
        結果のDataFrame.
    """
    rows = []
    for r in results:
        rows.append({
            "scenario_id": r.scenario_id,
            "scenario_name": r.scenario_name,
            "region": r.region,
            "item_count": len(r.items),
            "items": ";".join(r.items),
            "total_selling_price": r.total_selling_price,
            "fixed_shipping": r.fixed_shipping_revenue,
            "discount": r.discount_amount,
            "customer_payment": r.total_selling_price + r.fixed_shipping_revenue - r.discount_amount,
            "total_cost_price": r.total_cost_price,
            "actual_shipping_cost": r.actual_shipping_cost,
            "shipment_count": r.shipment_count,
            "gross_profit": r.gross_profit,
            "margin_rate": r.margin_rate,
            "margin_rate_pct": f"{r.margin_rate * 100:.1f}%",
            "margin_ok": r.margin_ok,
        })
    return pd.DataFrame(rows)


def sensitivity_analysis(
    scenarios: pd.DataFrame,
    products: pd.DataFrame,
    shipping_rates: pd.DataFrame,
    config: dict[str, Any],
    param_name: str,
    param_values: list[int],
) -> pd.DataFrame:
    """パラメータの感度分析を実行する.

    Args:
        scenarios: シナリオ一覧.
        products: 商品マスタ.
        shipping_rates: 配送料金テーブル.
        config: 基準設定.
        param_name: 変動させるパラメータ名
            ("shipping_buffer", "fixed_shipping", "discount_2", "discount_3", "discount_4").
        param_values: パラメータの変動値リスト.

    Returns:
        感度分析結果のDataFrame.
    """
    import copy

    rows = []
    for val in param_values:
        cfg = copy.deepcopy(config)

        if param_name == "shipping_buffer":
            cfg["layer1_markup"]["shipping_buffer_per_item"] = val
            # 販売価格も再計算
            prods = products.copy()
            margin_rate = cfg["layer1_markup"]["base_margin_rate"]
            prods["selling_price"] = (
                (prods["cost_price"] / (1 - margin_rate)).apply(lambda x: int(x)) + val
            )
        elif param_name == "fixed_shipping":
            cfg["layer2_fixed_shipping"]["display_amount"] = val
            prods = products.copy()
        elif param_name == "discount_2":
            cfg["layer3_discount"]["tiers"][0]["discount_amount"] = val
            prods = products.copy()
        elif param_name == "discount_3":
            cfg["layer3_discount"]["tiers"][1]["discount_amount"] = val
            prods = products.copy()
        elif param_name == "discount_4":
            cfg["layer3_discount"]["tiers"][2]["discount_amount"] = val
            prods = products.copy()
        else:
            prods = products.copy()

        results = run_all_scenarios(scenarios, prods, shipping_rates, cfg)
        for r in results:
            rows.append({
                "param_name": param_name,
                "param_value": val,
                "scenario_id": r.scenario_id,
                "scenario_name": r.scenario_name,
                "margin_rate": r.margin_rate,
                "gross_profit": r.gross_profit,
                "margin_ok": r.margin_ok,
            })
    return pd.DataFrame(rows)
