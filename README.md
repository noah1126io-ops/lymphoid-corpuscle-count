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
3. `Image metadata` に倍率、染色、標本ID、アノテーターなどを入力します。
4. `Drawing mode` で `circle` または `rect` を選び、画像上の細胞を囲みます。
5. 既存アノテーションの移動、リサイズ、削除は `transform` モードで行います。
6. `Export objective filter` で `all`, `20x`, `40x`, `other`, `unknown` から保存対象を選びます。
7. カウント表でラベル別の件数と合計を確認します。
8. `Save JSON / CSV` で `data/annotations/` と `data/exports/` に保存します。
9. 過去のJSONは `Restore annotations.json` から読み込むと復元できます。

## 画像メタデータ

必須項目:

- `objective_magnification`: `20x`, `40x`, `other`, `unknown`
- `staining`: `H&E`, `other`, `unknown`

任意項目:

- `total_magnification`
- `pixel_size_um`
- `tissue_type`
- `specimen_id`
- `scanner_or_microscope`
- `annotator`
- `notes`

入力したメタデータは保存時に各アノテーションへ展開されます。将来的に倍率別、染色別、標本別に学習データを分けるための列として利用できます。

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
  "image_metadata": {
    "objective_magnification": "20x",
    "staining": "H&E",
    "total_magnification": "400x",
    "pixel_size_um": "0.25",
    "tissue_type": "lung",
    "specimen_id": "case_001",
    "scanner_or_microscope": "scanner A",
    "annotator": "annotator name",
    "notes": ""
  },
  "export_objective_filter": "20x",
  "annotations": [
    {
      "image_name": "sample.tif",
      "label": "eosinophil",
      "x": 120.5,
      "y": 240.0,
      "width": 32.0,
      "height": 32.0,
      "confidence": 1.0,
      "objective_magnification": "20x",
      "staining": "H&E",
      "total_magnification": "400x",
      "pixel_size_um": "0.25",
      "tissue_type": "lung",
      "specimen_id": "case_001",
      "scanner_or_microscope": "scanner A",
      "annotator": "annotator name",
      "notes": "",
      "created_at": "2026-05-20T10:00:00"
    }
  ],
  "saved_at": "2026-05-20T10:05:00"
}
```

`x` と `y` は矩形または円の中心座標です。大きい画像は表示用に縮小されますが、保存時には `scale_factor` を使って元画像座標へ戻します。これにより、将来的にYOLO形式へ変換しやすい構造になっています。

カウントCSVは次の形式です。

```csv
label,count,objective_magnification,staining,total_magnification,pixel_size_um,tissue_type,specimen_id,scanner_or_microscope,annotator,notes,export_objective_filter
eosinophil,10,20x,H&E,400x,0.25,lung,case_001,scanner A,annotator name,,20x
neutrophil,8,20x,H&E,400x,0.25,lung,case_001,scanner A,annotator name,,20x
basophil,2,20x,H&E,400x,0.25,lung,case_001,scanner A,annotator name,,20x
other,1,20x,H&E,400x,0.25,lung,case_001,scanner A,annotator name,,20x
total,21,20x,H&E,400x,0.25,lung,case_001,scanner A,annotator name,,20x
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

各アノテーションは `image_name`, `label`, `x`, `y`, `width`, `height` と画像メタデータを元画像座標で保持します。YOLO形式では、画像幅と高さで正規化した中心座標と幅、高さが必要です。この保存形式から次のように直接変換できます。

```text
class_id x_center_norm y_center_norm width_norm height_norm
```

ラベル順は `eosinophil`, `neutrophil`, `basophil`, `other` として固定しているため、将来的にクラスIDへ安定して変換できます。

`objective_magnification` を使って `20x` と `40x` のデータを分けて保存できるため、倍率別の学習データセットや検証データセットを作成しやすい設計です。
