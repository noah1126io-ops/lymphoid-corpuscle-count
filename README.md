# Manual Granulocyte Annotation Tool

組織画像中の好酸球、好中球、好塩基球、その他の細胞を手動でアノテーションし、教師データとして保存するためのStreamlitアプリです。診断用途ではなく、研究用の教師データ作成を目的としたMVPです。

## セットアップ方法

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linuxの場合:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 実行方法

```bash
streamlit run app.py
```

ブラウザで表示されたローカルURLを開きます。

## 使い方

1. 右側の `Upload tissue image` から jpg / png / tif / tiff 画像をアップロードします。
2. 右側の `Active label` でラベルを選択します。
3. `Drawing mode` で `circle` または `rect` を選び、画像上の細胞を囲みます。
4. 既存アノテーションの移動、リサイズ、削除は `transform` モードで行います。
5. カウント表でラベル別の件数と合計を確認します。
6. `Save JSON / CSV` で `data/annotations/` と `data/exports/` に保存します。
7. 過去のJSONは `Restore annotations.json` から読み込むと復元できます。

## 保存されるデータ形式

アノテーションJSONは次の形式で保存されます。

```json
{
  "image_name": "sample.tif",
  "labels": ["eosinophil", "neutrophil", "basophil", "other"],
  "label_colors": {
    "eosinophil": "#e83e8c",
    "neutrophil": "#2f80ed",
    "basophil": "#7b2cbf",
    "other": "#6c757d"
  },
  "annotations": [
    {
      "image_name": "sample.tif",
      "label": "eosinophil",
      "x": 120.5,
      "y": 240.0,
      "width": 32.0,
      "height": 32.0,
      "confidence": 1.0,
      "created_at": "2026-05-20T10:00:00"
    }
  ],
  "saved_at": "2026-05-20T10:05:00"
}
```

`x` と `y` は矩形または円の中心座標です。大きい画像は表示用に縮小されますが、保存時には `scale_factor` を使って元画像座標へ戻します。これにより、将来的にYOLO形式へ変換しやすい構造になっています。

カウントCSVは次の形式です。

```csv
label,count
eosinophil,10
neutrophil,8
basophil,2
other,1
total,21
```

## ディレクトリ構成

```text
.
├── app.py
├── requirements.txt
├── README.md
└── data
    ├── images
    ├── annotations
    └── exports
```

## YOLO学習データへの変換設計

各アノテーションは `image_name`, `label`, `x`, `y`, `width`, `height` を元画像座標で保持します。YOLO形式では、画像幅と高さで正規化した中心座標と幅、高さが必要です。この保存形式から次のように直接変換できます。

```text
class_id x_center_norm y_center_norm width_norm height_norm
```

ラベル順は `eosinophil`, `neutrophil`, `basophil`, `other` として固定しているため、将来的にクラスIDへ安定して変換できます。
