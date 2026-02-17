"""メインシミュレーション実行スクリプト.

全シナリオのシミュレーション、感度分析、レポート生成を実行する。
結果は experiments/exp001_baseline/ に保存される。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import (
    load_config,
    load_products,
    load_scenarios,
    load_shipping_rates,
    validate_selling_prices,
)
from src.simulator import (
    results_to_dataframe,
    run_all_scenarios,
    sensitivity_analysis,
)
from src.visualizer import (
    plot_margin_bar,
    plot_price_validation,
    plot_profit_breakdown,
    plot_sensitivity,
)


def main() -> None:
    """メイン実行関数."""
    print("=" * 60)
    print("EEZO Shipping & Discount Simulation")
    print(f"Execution: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # --- データ読み込み ---
    print("\n[1/7] Loading data...")
    products = load_products()
    shipping_rates = load_shipping_rates()
    config = load_config()
    scenarios = load_scenarios()
    print(f"  Products: {len(products)} SKUs")
    print(f"  Shipping regions: {len(shipping_rates)}")
    print(f"  Scenarios: {len(scenarios)}")

    # --- 出力ディレクトリ ---
    exp_dir = PROJECT_ROOT / "experiments" / "exp001_baseline"
    exp_dir.mkdir(parents=True, exist_ok=True)

    # --- 販売価格検証 ---
    print("\n[2/7] Validating selling prices...")
    validated = validate_selling_prices(products, config)

    price_issues = validated[~validated["price_ok"]]
    market_issues = validated[validated["market_premium_ok"] == False]

    print(f"  Price below theoretical minimum: {len(price_issues)} items")
    if len(price_issues) > 0:
        for _, row in price_issues.iterrows():
            print(f"    - {row['sku']} ({row['name']}): selling={row['selling_price']}, min={row['theoretical_min_price']}")

    print(f"  Market premium exceeded (>15%): {len(market_issues)} items")
    if len(market_issues) > 0:
        for _, row in market_issues.iterrows():
            print(f"    - {row['sku']} ({row['name']}): premium={row['market_premium_rate']:.1%}")

    plot_price_validation(validated, exp_dir / "price_validation.png")
    validated.to_csv(exp_dir / "price_validation.csv", index=False)
    print("  -> price_validation.png / .csv saved")

    # --- 全シナリオシミュレーション ---
    print("\n[3/7] Running scenario simulation...")
    results = run_all_scenarios(scenarios, products, shipping_rates, config)
    results_df = results_to_dataframe(results)

    print("\n  --- Scenario Results ---")
    for _, row in results_df.iterrows():
        status = "OK" if row["margin_ok"] else "NG"
        print(f"  [{status}] {row['scenario_id']} {row['scenario_name']}: "
              f"margin={row['margin_rate_pct']}, profit={row['gross_profit']:,}")

    results_df.to_csv(exp_dir / "scenario_results.csv", index=False)
    print(f"\n  -> scenario_results.csv saved")

    ng_count = len(results_df[~results_df["margin_ok"]])
    ok_count = len(results_df[results_df["margin_ok"]])
    print(f"\n  Summary: {ok_count} OK / {ng_count} NG (out of {len(results_df)} scenarios)")

    # --- 粗利率グラフ ---
    print("\n[4/7] Generating margin chart...")
    min_margin = config["constraints"]["min_margin_rate"]
    plot_margin_bar(results_df, exp_dir / "margin_analysis.png", min_margin)
    print("  -> margin_analysis.png saved")

    # --- 収支内訳グラフ ---
    print("\n[5/7] Generating profit breakdown chart...")
    plot_profit_breakdown(results_df, exp_dir / "profit_breakdown.png")
    print("  -> profit_breakdown.png saved")

    # --- 感度分析 ---
    print("\n[6/7] Running sensitivity analysis...")

    # 転嫁額の感度分析
    sens_buffer = sensitivity_analysis(
        scenarios, products, shipping_rates, config,
        "shipping_buffer",
        [0, 200, 300, 400, 500, 600, 700, 800, 1000],
    )
    sens_buffer.to_csv(exp_dir / "sensitivity_buffer.csv", index=False)
    plot_sensitivity(sens_buffer, "Shipping Buffer per Item (JPY)",
                     exp_dir / "sensitivity_buffer.png", min_margin)
    print("  -> sensitivity_buffer.png / .csv saved")

    # 固定送料の感度分析
    sens_shipping = sensitivity_analysis(
        scenarios, products, shipping_rates, config,
        "fixed_shipping",
        [0, 500, 800, 1000, 1200, 1500, 2000],
    )
    sens_shipping.to_csv(exp_dir / "sensitivity_fixed_shipping.csv", index=False)
    plot_sensitivity(sens_shipping, "Fixed Shipping Display Amount (JPY)",
                     exp_dir / "sensitivity_fixed_shipping.png", min_margin)
    print("  -> sensitivity_fixed_shipping.png / .csv saved")

    # ディスカウント(2品)の感度分析
    sens_d2 = sensitivity_analysis(
        scenarios, products, shipping_rates, config,
        "discount_2",
        [0, 100, 200, 300, 400, 500, 700],
    )
    sens_d2.to_csv(exp_dir / "sensitivity_discount_2.csv", index=False)
    plot_sensitivity(sens_d2, "2-Item Discount Amount (JPY)",
                     exp_dir / "sensitivity_discount_2.png", min_margin)
    print("  -> sensitivity_discount_2.png / .csv saved")

    # --- レポート生成 ---
    print("\n[7/7] Generating report...")
    report = generate_report(results_df, validated, config, sens_buffer, ng_count, ok_count)
    report_path = exp_dir / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  -> report.md saved")

    # --- 詳細出荷グループ情報 ---
    shipment_rows = []
    for r in results:
        for g in r.shipment_groups:
            shipment_rows.append({
                "scenario_id": r.scenario_id,
                "supplier": g.supplier,
                "temp_zone": g.temp_zone,
                "item_count": g.item_count,
                "skus": ";".join(g.skus),
                "total_weight_g": g.total_weight_g,
                "total_cost": g.total_cost,
                "total_selling": g.total_selling,
            })
    shipment_df = pd.DataFrame(shipment_rows)
    shipment_df.to_csv(exp_dir / "shipment_groups.csv", index=False)
    print("  -> shipment_groups.csv saved")

    print("\n" + "=" * 60)
    print("Simulation complete!")
    print(f"All results saved to: {exp_dir}")
    print("=" * 60)


def generate_report(
    results_df: "pd.DataFrame",
    validated: "pd.DataFrame",
    config: dict,
    sens_buffer: "pd.DataFrame",
    ng_count: int,
    ok_count: int,
) -> str:
    """Markdownレポートを生成する."""
    import pandas as pd

    min_margin = config["constraints"]["min_margin_rate"]
    buffer = config["layer1_markup"]["shipping_buffer_per_item"]
    fixed_ship = config["layer2_fixed_shipping"]["display_amount"]
    tiers = config["layer3_discount"]["tiers"]

    report = f"""# EEZO 送料・ディスカウント シミュレーションレポート

**実行日**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**実験ID**: exp001_baseline

---

## 1. パラメータ設定

| パラメータ | 値 |
|-----------|-----|
| 基本マージン率 | {config['layer1_markup']['base_margin_rate']*100:.0f}% |
| 送料転嫁額/商品 | {buffer:,}円 |
| 固定送料（顧客表示） | {fixed_ship:,}円 |
| 最低粗利率 | {min_margin*100:.0f}% |

### ディスカウントティア

| 条件 | 割引額 |
|------|--------|
"""
    for t in tiers:
        report += f"| 同一仕入先 {t['min_items']}品以上 | {t['discount_amount']:,}円 |\n"

    report += f"""
---

## 2. 販売価格検証

- 理論最低価格を下回る商品: **{len(validated[~validated['price_ok']])}件**
- 市場プレミアム率超過（>15%）: **{len(validated[validated['market_premium_ok'] == False])}件**

![販売価格 vs 市場参考価格](price_validation.png)

---

## 3. シナリオ別シミュレーション結果

| ID | シナリオ | 地域 | 商品数 | 販売価格計 | 送料収入 | 割引 | 顧客支払 | 仕入原価 | 実配送費 | 出荷数 | 粗利 | 粗利率 | 判定 |
|-----|---------|------|--------|-----------|---------|------|---------|---------|---------|--------|------|--------|------|
"""
    for _, r in results_df.iterrows():
        status = "OK" if r["margin_ok"] else "**NG**"
        report += (
            f"| {r['scenario_id']} | {r['scenario_name']} | {r['region']} | "
            f"{r['item_count']} | {r['total_selling_price']:,} | {r['fixed_shipping']:,} | "
            f"{r['discount']:,} | {r['customer_payment']:,} | {r['total_cost_price']:,} | "
            f"{r['actual_shipping_cost']:,} | {r['shipment_count']} | {r['gross_profit']:,} | "
            f"{r['margin_rate_pct']} | {status} |\n"
        )

    report += f"""
**判定結果**: {ok_count} OK / {ng_count} NG（全{len(results_df)}シナリオ）

![シナリオ別粗利率](margin_analysis.png)

![収支内訳](profit_breakdown.png)

---

## 4. 感度分析

### 送料転嫁額（shipping_buffer_per_item）

転嫁額を0〜1,000円で変動させた場合の各シナリオの粗利率推移。

![感度分析: 転嫁額](sensitivity_buffer.png)

### 固定送料表示額

固定送料を0〜2,000円で変動させた場合の各シナリオの粗利率推移。

![感度分析: 固定送料](sensitivity_fixed_shipping.png)

### 2品目ディスカウント額

2品目割引を0〜700円で変動させた場合の各シナリオの粗利率推移。

![感度分析: 2品目割引](sensitivity_discount_2.png)

---

## 5. 境界ケース分析

"""
    worst = results_df.loc[results_df["margin_rate"].idxmin()]
    best = results_df.loc[results_df["margin_rate"].idxmax()]

    report += f"""### 最悪ケース
- **{worst['scenario_id']} {worst['scenario_name']}**: 粗利率 {worst['margin_rate_pct']}、粗利 {worst['gross_profit']:,}円
- 要因: 低単価商品の単品購入 + 遠方配送で実配送コストが高い

### 最良ケース
- **{best['scenario_id']} {best['scenario_name']}**: 粗利率 {best['margin_rate_pct']}、粗利 {best['gross_profit']:,}円
- 要因: 高単価商品のまとめ買い + 近場配送で効率が良い

---

## 6. 考察と推奨事項

"""
    if ng_count > 0:
        report += f"""### 課題
- **{ng_count}シナリオが最低粗利率{min_margin*100:.0f}%を下回っている**
- 特に低単価単品・遠方配送のケースで粗利が確保できない

### 推奨アクション
1. **低単価商品の送料転嫁額を引き上げ**（現在{buffer}円 → 検討値: 700〜800円）
2. **遠方地域への追加送料**の検討（沖縄・九州は+500〜1,000円）
3. **最低購入金額の設定**（例: 3,000円以上で送料1,000円、未満は1,500円）
"""
    else:
        report += f"""### 良好な結果
- **全{len(results_df)}シナリオで粗利率{min_margin*100:.0f}%以上を確保**
- 現行パラメータで顧客体験と収益性の両立が可能

### 推奨アクション
1. 現行パラメータでShopifyへの実装を進める
2. 実運用後のデータで定期的にシミュレーションを再実行
3. 新規仕入先の追加時は本シミュレーションで事前検証
"""

    report += f"""
---

## 7. ファイル一覧

| ファイル | 内容 |
|---------|------|
| scenario_results.csv | シナリオ別シミュレーション結果 |
| price_validation.csv | 販売価格検証結果 |
| shipment_groups.csv | 出荷グループ詳細 |
| margin_analysis.png | 粗利率棒グラフ |
| profit_breakdown.png | 収支内訳グラフ |
| price_validation.png | 販売価格 vs 市場価格散布図 |
| sensitivity_buffer.png | 感度分析: 転嫁額 |
| sensitivity_fixed_shipping.png | 感度分析: 固定送料 |
| sensitivity_discount_2.png | 感度分析: 2品目割引 |
| report.md | 本レポート |
"""
    return report


if __name__ == "__main__":
    import pandas as pd
    main()
