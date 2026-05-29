# Manual Granulocyte Annotation Tool

ECRS、鼻茸、副鼻腔粘膜などのH&E病理画像から、好酸球を中心に手動アノテーションし、将来的なAI検出モデルの教師データを作成するためのStreamlitアプリです。

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

NDPIファイルを扱う場合は、`openslide-python`, `openslide-bin`, `tifffile`, `numpy` が必要です。これらは `requirements.txt` に含まれています。Cellpose / Cellpose-SAM は必須依存には含めていません。

## 実行方法

```bash
streamlit run app.py
```

ブラウザで表示されたローカルURLを開きます。

## ECRS / Nasal Polyp Template

`ECRS_nasal_polyp` テンプレートは、H&E染色された鼻茸または副鼻腔粘膜画像における好酸球カウント支援データ作成を想定しています。

初期評価の主対象は `eosinophil` vs `other_cell` / `ignore` です。将来的な拡張のため、次のラベルも保持します。

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

Cellposeや自前モデルなどの外部候補を将来取り込めるように、アノテーションごとに候補由来と確認状態を保存します。ただし、Cellpose自体は必須依存には含めていません。

## 使い方

1. `Upload tissue image` から jpg / png / tif / tiff / ndpi 画像をアップロードします。
2. `Project Template` で `ECRS_nasal_polyp` などを選びます。
3. `Image Metadata` に疾患背景、組織種、染色、倍率、標本ID、アノテーターなどを入力します。
4. `Region Type` で画像全体の領域タイプを選びます。
5. `Active Label` でラベルを選択します。
6. `Drawing Mode` で `circle` または `rect` を選び、細胞を囲みます。
7. `Export Settings` で倍率フィルタやYOLOの `ignore` 除外を設定します。
8. `Save / Restore` から過去の `annotations.json` を読み込めます。
9. 画面下部の `Save exports` で各種ファイルを保存します。

## NDPI to OME-TIFF

NDPIファイルはPillowだけでは直接読み込めないため、OpenSlideで読み込みます。巨大なWSI全体をcanvasへ直接載せるのではなく、低倍率thumbnailでROIを選択し、patch画像を作成してから既存のアノテーション画面に表示します。

- 元のWSI/NDPI: `data/images/original_wsi/<file_name>`
- patch画像: `data/patches/images/<wsi_stem>_<patch_id>.png`

初期MVPでは、ROI矩形または指定座標から `1024 x 1024` または `2048 x 2048` のpatchを作ります。patch画像を学習画像として扱うため、YOLO座標はpatch内座標で正規化されます。

WSI由来のannotationでは、patch内座標に加えて、親WSI上の座標も保存します。

旧MVPのNDPI全体をOME-TIFFへ変換する補助関数は残していますが、通常のアノテーションではWSI patch workflowを使います。

## Multi-Tissue Eosinophil Reference Dataset

副鼻腔炎画像が届くまで、肝臓など他臓器H&E画像を含む汎用好酸球reference datasetを作成できます。`project_template` と `source_organ` で、ECRS本命データと汎用referenceデータを分けて管理してください。

- ECRS本命データ: `project_template=ECRS_nasal_polyp`, `source_organ=sinonasal_mucosa`
- 汎用referenceデータ: `project_template=generic_eosinophil_reference` または `multi_tissue_eosinophil_reference`
- 臓器分類: `source_organ=liver / sinonasal_mucosa / esophagus / skin / lung / other / unknown`

## Project Templates

選択できるテンプレート:

- `ECRS_nasal_polyp`
- `CRS_sinonasal_mucosa`
- `EoE_esophagus_reference`
- `GI_eosinophilia_reference`
- `generic_eosinophil_reference`
- `multi_tissue_eosinophil_reference`
- `generic_granulocyte`
- `custom`

テンプレートを選ぶと、推奨される `disease_context`, `tissue_type`, `staining`, `objective_magnification` などが自動設定されます。

## 保存されるメタデータ

メタデータは画像単位の情報として入力します。保存時には、各アノテーション行、画像ごとのcountファイル、集計用の `dataset_manifest.csv` に展開されます。

必須項目:

- `project_template`
- `disease_context`
- `source_organ`
- `tissue_type`
- `tissue_region`
- `staining`
- `objective_magnification`
- `specimen_id`
- `slide_id`
- `annotator`

任意項目:

- `patient_id_hash`
- `anatomical_site`
- `scanner_or_microscope`
- `pixel_size_um`
- `hpf_area_mm2`
- `hpf_diameter_mm`
- `image_is_single_hpf`
- `section_quality`
- `reviewed`
- `exported`
- `source_wsi_name`
- `patch_id`
- `patch_x`
- `patch_y`
- `patch_width`
- `patch_height`
- `target_mpp`
- `mpp_x`
- `mpp_y`
- `notes`

MVPでは必須項目が空でも保存できますが、保存前にwarningを表示します。

## メタデータ項目の説明

| 項目 | 必須 | 説明 |
|---|---:|---|
| `project_template` | はい | 解析目的や対象組織に応じたテンプレートです。ECRS鼻茸、CRS副鼻腔粘膜、EoE参照、GI好酸球症参照、汎用顆粒球、カスタムを区別します。テンプレート別に推奨ラベルや初期メタデータを変えるために使います。 |
| `disease_context` | はい | 画像が属する疾患・臨床研究上の背景です。自由入力できます。例: `ECRS`, `CRSwNP`, `CRSsNP`, `eosinophilic_inflammation`, `control`, `unknown`。疾患群別の集計や学習データ分割に使います。 |
| `source_organ` | いいえ | WSIまたはpatchの由来臓器です。例: `liver`, `sinonasal_mucosa`, `esophagus`, `skin`, `lung`, `other`, `unknown`。ECRS本命データとmulti-tissue reference dataを分けるために使います。 |
| `tissue_type` | はい | 標本の組織種です。例: `nasal_polyp`, `sinonasal_mucosa`, `inferior_turbinate`, `other`, `unknown`。組織ごとの好酸球分布やモデル性能を比較するために使います。 |
| `tissue_region` | いいえ | patch内または画像内の組織領域です。例: `portal_tract`, `lobule`, `interface_area`, `bile_duct_area`, `lamina_propria`, `epithelium`, `other`, `unknown`。臓器内領域別の評価に使います。 |
| `staining` | はい | 染色法です。初期想定は `H&E` です。染色条件が異なる画像を混ぜて学習・評価しないための管理項目です。 |
| `objective_magnification` | はい | 対物レンズ倍率です。例: `20x`, `40x`, `other`, `unknown`。倍率別にデータを分ける、またはYOLO学習用にフィルタするために使います。 |
| `specimen_id` | はい | 標本単位の匿名化IDです。患者氏名やカルテ番号などの直接識別子は入れず、研究内で追跡可能なIDを使います。 |
| `slide_id` | はい | スライド単位の匿名化IDです。同一標本から複数スライドがある場合に区別します。 |
| `annotator` | はい | アノテーション実施者のIDまたは名前です。複数アノテーター間の一致率確認やレビュー管理に使います。 |
| `patient_id_hash` | いいえ | 患者単位で画像をまとめるための匿名化・ハッシュ化IDです。直接識別子は保存しないでください。患者単位でtrain/val/testを分ける場合に有用です。 |
| `anatomical_site` | いいえ | 採取部位です。例: `ethmoid_sinus`, `maxillary_sinus`, `nasal_cavity`, `other`, `unknown`。部位別の炎症分布やモデル評価に使います。 |
| `scanner_or_microscope` | いいえ | 画像取得に使ったスキャナー、顕微鏡、カメラなどの情報です。施設差・機器差による色調や解像度の違いを確認するために使います。 |
| `pixel_size_um` | いいえ | 1ピクセルあたりの実寸をマイクロメートル単位で入力します。`eos/mm²` の計算に必要です。未入力の場合、面積換算はできません。 |
| `hpf_area_mm2` | いいえ | 1 high-power fieldの面積をmm²単位で入力します。`eos/HPF` を `eos/mm² * hpf_area_mm2` として換算するために使います。顕微鏡・接眼レンズ条件により異なります。 |
| `hpf_diameter_mm` | いいえ | HPFの視野直径をmm単位で記録する項目です。現時点では主に記録用で、必要に応じて `hpf_area_mm2` の確認に使えます。 |
| `image_is_single_hpf` | いいえ | 画像全体がちょうど1 HPFであることを明示するチェックです。`pixel_size_um` がない場合でも、このチェックがある場合のみ `eos_per_HPF = eosinophil_count` として保存できます。 |
| `section_quality` | いいえ | 切片・画像品質です。例: `good`, `acceptable`, `poor`。ぼけ、折れ、染色不良、圧挫などがある画像を後で除外・層別化するために使います。 |
| `reviewed` | いいえ | 人が確認済みで学習候補にできる画像であることを示す管理フラグです。YOLO学習用エクスポートで対象画像を絞るために使います。 |
| `exported` | いいえ | 学習用・共有用などにエクスポート済みであることを示す管理フラグです。再エクスポートやデータセット管理に使います。 |
| `source_wsi_name` | いいえ | patchの親WSIファイル名です。patch画像がどのNDPI/WSIから作られたかを追跡します。 |
| `patch_id` | いいえ | patch単位のIDです。初期MVPでは `patch_x..._y..._size` 形式で自動生成されます。 |
| `patch_x` | いいえ | patch左上のWSI level 0 X座標です。 |
| `patch_y` | いいえ | patch左上のWSI level 0 Y座標です。 |
| `patch_width` | いいえ | patch幅です。初期UIでは `1024` または `2048` pxを選べます。 |
| `patch_height` | いいえ | patch高さです。初期UIでは `1024` または `2048` pxを選べます。 |
| `target_mpp` | いいえ | patch作成時に想定した目標mppです。初期MVPでは記録項目です。 |
| `mpp_x` | いいえ | OpenSlideから取得した親WSIのX方向mppです。取得できない場合は空欄になります。 |
| `mpp_y` | いいえ | OpenSlideから取得した親WSIのY方向mppです。取得できない場合は空欄になります。 |
| `notes` | いいえ | 自由記載欄です。染色の癖、アーチファクト、判定に迷った点、共同研究上の補足などを記録できます。 |

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
- `eos_per_HPF`: HPFあたりの推定好酸球数
- `eos_per_mm2`: 1 mm²あたりの推定好酸球数

面積換算は `pixel_size_um` が入力され、元画像サイズが取得できる場合のみ行います。

```text
image_area_mm2 = image_width_px * image_height_px * (pixel_size_um / 1000)^2
eos_per_mm2 = eosinophil_count / image_area_mm2
eos_per_HPF = eos_per_mm2 * hpf_area_mm2
```

`pixel_size_um` が未入力の場合、`eos_per_mm2` と `eos_per_HPF` は `not_calculated` として保存されます。ただし、画像全体がちょうど1 HPFであることを `Image is exactly 1 HPF` で明示した場合のみ、`eos_per_HPF = eosinophil_count` として保存できます。

## Export Files

保存されるファイル:

- `data/annotations/<export_file_stem>_annotations.json`
- `data/exports/<export_file_stem>_annotations.csv`
- `data/exports/<export_file_stem>_counts.csv`
- `data/exports/yolo_labels/<export_file_stem>.txt`
- `data/exports/dataset_manifest.csv`
- `data/exports/annotations.csv`
- `data/exports/counts.csv`
- `data/exports/metadata.csv`

`export_file_stem` は原則として次の形式で作られます。

```text
<specimen_id>_<slide_id>_<image_stem>
```

`specimen_id` または `slide_id` が未入力の場合は、入力済みのIDと画像名から作られます。両方が未入力の場合は従来通り画像名ベースになります。そのため、別症例で同じ `sample.tif` のような画像名を使う場合は、`specimen_id` と `slide_id` を入力してから保存してください。

画像ごとのファイルは、別画像を保存しても上書きされにくい形式です。同じ `specimen_id`、`slide_id`、画像名の組み合わせを再保存した場合は、その画像の annotation JSON/CSV、counts CSV、YOLO label が更新されます。

`dataset_manifest.csv` は画像単位の管理表です。保存時に `data/annotations/*_annotations.json` を読み直して再生成されるため、複数画像の管理表として使えます。集計用の `annotations.csv` と `counts.csv` も同じタイミングで再生成されます。

`metadata.csv` はannotation単位のメタデータ表です。WSI patch workflowでは、patch内座標とWSI全体座標を含むため、後でhotspot解析や親WSI上への再投影に使えます。

`reviewed` と `exported` は、human-confirmed annotation を学習用に使うための管理フラグです。

`dataset_manifest.csv` には、各画像に対応する出力ファイルを追跡しやすいように、次のパス列も保存されます。

- `annotation_json_path`
- `annotation_csv_path`
- `count_csv_path`
- `yolo_label_path`

## Annotation Coordinates

各アノテーションには、hotspot集計やYOLO変換に使える座標を保存します。

- `x_original`
- `y_original`
- `bbox_width_original`
- `bbox_height_original`
- `x_in_display`
- `y_in_display`
- `scale_factor`
- `x_in_patch`
- `y_in_patch`
- `x_wsi`
- `y_wsi`
- `patch_x`
- `patch_y`
- `source_wsi_name`
- `patch_id`

後方互換のため、従来の `x`, `y`, `width`, `height` も元画像座標として保持します。

patch画像でアノテーションする場合、`x_original` と `y_original` はpatch画像内座標です。`x_wsi` と `y_wsi` は `patch_x + x_in_patch`, `patch_y + y_in_patch` として保存され、親WSI上の位置を追跡できます。

## Annotation Status

AI候補提示や外部ツール由来の候補を、手動で確定したアノテーションと区別するため、各アノテーションに次のフィールドを保存します。

- `candidate_source`: `manual`, `imported_cellpose`, `imported_custom_model`, `model_v1`
- `annotation_status`: `confirmed_by_human`, `corrected_by_human`, `candidate_unconfirmed`, `rejected`
- `used_for_training`: `true` または `false`

手動で描いたアノテーションは、デフォルトで次の値になります。

```json
{
  "candidate_source": "manual",
  "annotation_status": "confirmed_by_human",
  "used_for_training": true
}
```

将来的にCellposeや自前モデルから候補を読み込む場合、未確認候補は原則として次の扱いにします。

```json
{
  "candidate_source": "imported_cellpose",
  "annotation_status": "candidate_unconfirmed",
  "used_for_training": false
}
```

`rejected` のアノテーションは、`used_for_training=false` として扱います。YOLO export、将来のcrop export、training dataset exportでは、`used_for_training=true` のアノテーションだけを使います。これにより、human-confirmed annotationのみを学習用に使う方針を保てます。

## YOLO変換

YOLO形式は次の形式で保存されます。

```text
class_id x_center_norm y_center_norm width_norm height_norm
```

座標は元画像サイズで正規化されます。`ignore` ラベルは、UIのチェックボックスでYOLO出力から除外できます。さらに、YOLO出力には `used_for_training=true` のアノテーションのみが含まれます。

## YOLO学習用エクスポート

`Generate YOLO training dataset` を押すと、保存済みの画像別 annotation JSON からYOLO学習用ディレクトリを生成します。

```text
data/dataset/
├── images/
├── labels/
└── data.yaml
```

初期設定では `reviewed` または `exported` が付いた画像だけを対象にします。これは、完全手動で確認された human-confirmed annotation のみを学習用に使うためです。`ignore` ラベルは `Exclude ignore from YOLO export` により除外できます。各画像内では `used_for_training=true` のアノテーションのみがYOLO labelへ変換されます。

WSI patch workflowでは、YOLO学習画像は親NDPI/WSIではなく `data/patches/images/` に保存されたpatch画像です。YOLO座標はpatch画像内で正規化されます。親WSI上の座標は `metadata.csv` と `annotations.json` に保持されます。

現時点のMVPでは train / val / test の厳密な分割は行わず、同じ `images` ディレクトリを `data.yaml` の train / val / test に指定します。これは動作確認用の暫定仕様です。

評価用データセットを作る次段階では、同一患者・同一標本由来の画像がtrainとval/testにまたがらないように、`specimen_id` や `patient_id_hash` 単位で train / val / test を分ける必要があります。将来的には `dataset_manifest.csv` を使って分割を管理します。

## ディレクトリ構成

```text
.
├── app.py
├── requirements.txt
├── README.md
└── data
    ├── images
    │   ├── converted
    │   ├── original_ndpi
    │   └── original_wsi
    ├── patches
    │   └── images
    ├── annotations
    ├── dataset
    │   ├── images
    │   └── labels
    └── exports
        └── yolo_labels
```

## 研究利用と倫理

このツールは診断用途ではなく、研究用・教師データ作成用です。臨床診断、治療方針決定、病理診断の代替として使用しないでください。

公開Web上の病理画像を無断で使用するのではなく、倫理審査、共同研究契約、データ利用契約などに基づいて取得された匿名化病理画像を使用してください。`patient_id_hash` などの項目は、直接識別子を保存しないための補助項目です。

## 今後の拡張予定

- AIによる好酸球候補提示
- hotspot top N 検出
- 領域ポリゴンごとの `region_type` 管理
- 病理医確認UI
- YOLO / COCO / WSIタイル分割エクスポート
- 倍率別・施設別・標本種別の検証データセット作成
