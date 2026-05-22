# Manual Granulocyte Annotation Tool

ECRS（好酸球性副鼻腔炎）、鼻茸、副鼻腔粘膜などのH&E病理画像から、好酸球を中心に手動アノテーションし、将来的なAI検出モデルの教師データを作成するためのStreamlitアプリです。

本アプリは研究用・定量補助用のMVPです。診断用途ではありません。

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

## ECRS / Nasal Polyp Template

`ECRS_nasal_polyp` テンプレートは、H&E染色された鼻茸または副鼻腔粘膜画像における好酸球カウント支援データ作成を想定しています。

このテンプレートでは、初期評価の主対象を `eosinophil` vs `other_cell` / `ignore` としつつ、将来的な拡張のために以下のラベルを保持します。

- `eosinophil`
- `neutrophil`
- `basophil`
- `mast_cell`
- `lymphocyte`
- `plasma_cell`
- `other_cell`
- `artifact`
- `ignore`

YOLOクラスIDは次の固定順です。

```text
0 eosinophil
1 neutrophil
2 basophil
3 mast_cell
4 lymphocyte
5 plasma_cell
6 other_cell
7 artifact
8 ignore
```

YOLO学習用エクスポートでは、`ignore` を除外できます。

## 使い方

サイドバーは次の順番です。

1. `Upload tissue image` から jpg / png / tif / tiff 画像をアップロードします。
2. `Project Template` で `ECRS_nasal_polyp` などを選びます。
3. `Image Metadata` に疾患背景、組織種、染色、倍率、標本ID、アノテーターなどを入力します。
4. `Region Type` で画像全体の領域タイプを選びます。
5. `Active Label` でラベルを選択します。
6. `Drawing Mode` で `circle` または `rect` を選び、細胞を囲みます。
7. `Export Settings` で倍率フィルタやYOLOの `ignore` 除外を設定します。
8. `Save / Restore` から過去の `annotations.json` を読み込めます。
9. 画面下部の `Save exports` で各種ファイルを保存します。

## Project Templates

選択できるテンプレート:

- `ECRS_nasal_polyp`
- `CRS_sinonasal_mucosa`
- `EoE_esophagus_reference`
- `GI_eosinophilia_reference`
- `generic_granulocyte`
- `custom`

テンプレートを選ぶと、推奨される `disease_context`, `tissue_type`, `staining`, `objective_magnification` などが自動設定されます。

## 保存されるメタデータ

必須項目:

- `project_template`
- `disease_context`: `ECRS`, `CRSwNP`, `CRSsNP`, `control`, `unknown`
- `tissue_type`: `nasal_polyp`, `sinonasal_mucosa`, `inferior_turbinate`, `other`, `unknown`
- `staining`: `H&E`, `other`, `unknown`
- `objective_magnification`: `20x`, `40x`, `other`, `unknown`
- `specimen_id`
- `slide_id`
- `annotator`

任意項目:

- `patient_id_hash`
- `anatomical_site`: `ethmoid_sinus`, `maxillary_sinus`, `nasal_cavity`, `other`, `unknown`
- `scanner_or_microscope`
- `pixel_size_um`
- `hpf_area_mm2`
- `hpf_diameter_mm`
- `section_quality`: `good`, `acceptable`, `poor`
- `notes`

入力したメタデータは画像ごとの annotation JSON/CSV、counts CSV、集約用の `dataset_manifest.csv` に保存されます。各アノテーション行にもメタデータが展開されるため、倍率別・疾患背景別・組織種別の再学習や検証に使いやすい形式です。

## Region Type

初期実装では画像全体の `global_region_type` を保存します。

選択肢:

- `epithelium`
- `lamina_propria`
- `glandular_area`
- `vascular_area`
- `mucus`
- `blood_clot`
- `necrosis`
- `artifact`
- `unknown`

保存形式には `region_annotations` を含めています。将来的にポリゴン単位の領域アノテーションを追加できる構造です。

## Count Metrics

ECRSテンプレートでは以下を表示・保存します。

- `eosinophil_count`: 好酸球としてアノテーションされた数
- `total_annotated_count`: `ignore` を除いた全アノテーション数
- `eosinophil_ratio`: `eosinophil_count / total_annotated_count`
- `eos_per_HPF`: `hpf_area_mm2` が入力されている場合のHPF換算値
- `eos_per_mm2`: `hpf_area_mm2` が入力されている場合の面積あたり換算値

面積換算は `pixel_size_um` が入力され、元画像サイズが取得できる場合のみ行います。

```text
image_area_mm2 = image_width_px * image_height_px * (pixel_size_um / 1000)^2
eos_per_mm2 = eosinophil_count / image_area_mm2
eos_per_HPF = eos_per_mm2 * hpf_area_mm2
```

`pixel_size_um` が未入力の場合、`eos_per_mm2` と `eos_per_HPF` は `not_calculated` として保存されます。ただし、画像全体がちょうど1 HPFであることを `Image is exactly 1 HPF` で明示した場合のみ、`eos_per_HPF = eosinophil_count` として保存できます。

## Export Files

保存されるファイル:

- `data/annotations/<image_stem>_annotations.json`
- `data/exports/<image_stem>_annotations.csv`
- `data/exports/<image_stem>_counts.csv`
- `data/exports/yolo_labels/<image_stem>.txt`
- `data/exports/dataset_manifest.csv`
- `data/exports/annotations.csv`
- `data/exports/counts.csv`

画像ごとのファイルは、別画像を保存しても上書きされません。同じ画像名を再保存した場合は、その画像の annotation JSON/CSV、counts CSV、YOLO label が更新されます。

`dataset_manifest.csv` は画像単位の管理表です。保存時に `data/annotations/*_annotations.json` を読み直して再生成されるため、複数画像の管理表として使えます。集約版の `annotations.csv` と `counts.csv` も同じタイミングで再生成されます。

`reviewed` と `exported` は、human-confirmed annotation を学習用に使うための管理フラグです。MVPでは保存前に必須メタデータが空の場合でも保存は可能ですが、警告が表示されます。

保存項目:

- `image_name`
- `original_image_path`
- `project_template`
- `disease_context`
- `tissue_type`
- `staining`
- `objective_magnification`
- `pixel_size_um`
- `hpf_area_mm2`
- `annotator`
- `reviewed`
- `exported`
- `annotation_count`
- `eosinophil_count`
- `saved_at`

## Annotation Coordinates

各アノテーションには、hotspot集計やYOLO変換に使える座標を保存します。

- `x_original`
- `y_original`
- `bbox_width_original`
- `bbox_height_original`
- `x_in_display`
- `y_in_display`
- `scale_factor`

後方互換のため、従来の `x`, `y`, `width`, `height` も元画像座標として保持します。

## YOLO変換

YOLO形式は次の形式で保存されます。

```text
class_id x_center_norm y_center_norm width_norm height_norm
```

座標は元画像サイズで正規化されます。`ignore` ラベルは、UIのチェックボックスでYOLO出力から除外できます。

## YOLO学習用エクスポート

`Generate YOLO training dataset` を押すと、保存済みの画像別 annotation JSON からYOLO学習用ディレクトリを生成します。

```text
data/dataset/
├── images/
├── labels/
└── data.yaml
```

初期設定では `reviewed` または `exported` が付いた画像だけを対象にします。これは、完全手動で確認された human-confirmed annotation のみを学習用に使うためです。`ignore` ラベルは `Exclude ignore from YOLO export` により除外できます。

現時点のMVPでは train / val / test の厳密な分割は行わず、同じ `images` ディレクトリを `data.yaml` の train / val / test に指定します。将来的に `dataset_manifest.csv` を使って分割を管理できます。

## ディレクトリ構成

```text
.
├── app.py
├── requirements.txt
├── README.md
└── data
    ├── images
    ├── annotations
    ├── dataset
    │   ├── images
    │   └── labels
    └── exports
        └── yolo_labels
```

## 研究利用と倫理

このツールは診断用途ではなく、研究用・教師データ作成用です。臨床診断、治療方針決定、病理診断の代替として使用しないでください。

公開Web上の病理画像を無断で使用するのではなく、倫理審査・共同研究・データ利用契約などに基づいて取得された匿名化病理画像を使用してください。`patient_id_hash` などの項目は、直接識別子を保存しないための補助項目です。

## 今後の拡張予定

- AIによる好酸球候補提示
- hotspot top N 検出
- 領域ポリゴンごとの `region_type` 管理
- 病理医確認UI
- YOLO / COCO / WSIタイル分割エクスポート
- 倍率別・施設別・標本種別の検証データセット作成
