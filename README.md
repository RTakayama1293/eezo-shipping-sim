# EEZO Shipping Simulator

EEZO（北海道食材EC）のShopify移行に伴う送料・ディスカウントロジックのシミュレーター。

## 目的

3層構造（商品価格転嫁＋固定送料＋合わせ買い割引）で、全購買シナリオにおいて粗利率15%以上を確保しつつ、顧客体験を最適化するパラメータを決定する。

## クイックスタート

```bash
pip install -r requirements.txt
```

### Claude Code on the Webでの使い方

1. このリポジトリをGitHubにpush
2. https://claude.ai/code でリポジトリを選択
3. 「全シナリオでシミュレーション実行して」と指示

## ディレクトリ構成

```
eezo-shipping-sim/
├── CLAUDE.md              # プロジェクト指示書（Claude Code用）
├── README.md
├── requirements.txt
├── .gitignore
├── .claude/
│   └── settings.json      # フック設定
├── data/
│   ├── raw/               # 元データ（編集禁止）
│   │   ├── config.json    # シミュレーション設定パラメータ
│   │   ├── products.csv   # 商品マスタ
│   │   ├── shipping_rates.csv  # 配送料金テーブル
│   │   └── scenarios.csv  # 検証シナリオ
│   └── processed/
├── experiments/            # 各シミュレーション結果
├── rules/                  # コーディングルール
├── skills/                 # ドメイン知識・ワークフロー
├── scripts/
│   └── setup.sh
├── src/                    # シミュレーションエンジン
└── outputs/                # 最終成果物
```

## データファイル

| ファイル | 内容 | 編集 |
|---------|------|------|
| config.json | 3層構造のパラメータ | パラメータ変更時のみ |
| products.csv | 商品マスタ（仕入原価・販売価格） | 商品追加・変更時 |
| shipping_rates.csv | ヤマト運輸クール便料金 | 料金改定時 |
| scenarios.csv | 購買シナリオ定義 | シナリオ追加時 |
