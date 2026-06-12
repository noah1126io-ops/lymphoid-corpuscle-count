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

このリポジトリでは `.streamlit/config.toml` でアップロード上限を `2048 MB` に設定しています。Streamlitの既定値は `200 MB` なので、大きなNDPI/WSIを扱う場合はこの設定が必要です。さらに大きいファイルを扱う場合は、PCのメモリと保存容量を確認したうえで `maxUploadSize` を調整してください。

Windowsでは、設定を確実に反映するため、次の起動スクリプトを使うことを推奨します。

```powershell
.\run_app.ps1
```

または:

```bat
run_app.bat
```

これらのスクリプトはアプリのフォルダへ移動してから、`--server.maxUploadSize=2048`、`--server.headless=true`、`--server.showEmailPrompt=false`、`--browser.gatherUsageStats=false` を明示してStreamlitを起動します。初回起動時のEmail入力プロンプトで起動が止まる場合にも、このスクリプトから起動してください。設定変更後は、起動中のStreamlitを一度停止してから再起動してください。

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

Cellpose、Open-EoE、自前モデルなどの外部候補を取り込めるように、アノテーションごとに候補由来と確認状態を保存します。ただし、CellposeやOpen-EoE自体は必須依存には含めていません。

## 使い方

アプリ上部の「はじめに: アプリ全体の操作ガイド」でも、同じ手順を確認できます。

1. 左サイドバーの「画像アップロード」から jpg / png / tif / tiff / ndpi 画像を選びます。
2. NDPI/WSIでは「自動patch queue」を生成し、確認するpatchを開きます。通常画像はそのままcanvasへ進みます。
3. 「プロジェクトテンプレート」と「画像メタデータ」で標本ID、slide ID、臓器、染色、倍率、annotatorを確認します。
4. 「確認モード」を選びます。通常レビューはqueue順、陽性探索はpriorityやclusterを用いた候補順です。
5. 「アクティブラベル」と「描画モード」を選び、細胞を円または矩形で囲みます。
6. 好酸球があるpatchは「好酸球あり: 保存して次へ」、ないpatchは「好酸球なし: 陰性保存して次へ」を押します。
7. 迷うpatchは「要再確認」、確認対象外は「今回はスキップ」を使用します。
8. annotation作業後、必要な場合だけYOLOまたはCLAM-compatible学習用データを生成します。

### 確認モードと保存データ

`通常レビュー`と`陽性探索`で保存されるannotation、metadata、patch status、座標形式は同じです。変わるのはqueueの絞り込みと次に表示するpatchの順番だけです。

| 操作 | 保存 | patch status | 次へ移動 |
| --- | --- | --- | --- |
| 好酸球あり: 保存して次へ | する | `done` | する |
| 好酸球なし: 陰性保存して次へ | する | `reviewed_empty` | する |
| 現在の内容を保存（移動しない） | する | `done` | しない |
| 前のpatch / 次のpatch | しない | 変更しない | する |
| 今回はスキップして次へ | annotationは確定保存しない | `skipped` | する |
| 要再確認にして次へ | annotationは確定保存しない | `flagged` | する |

陽性探索にある「詳細: 保存せずstatusだけを変更する」は、候補の整理だけを行う補助操作です。通常はこの詳細欄を開かず、好酸球あり/なしの保存ボタンを使用してください。

## NDPI to OME-TIFF

NDPIファイルはPillowだけでは直接読み込めないため、OpenSlideで読み込みます。巨大なWSI全体をcanvasへ直接載せるのではなく、WSIビューアでマウスホイールズームとドラッグ移動を行い、patchプレビューで位置を確認してから既存のアノテーション画面に表示します。

- 元のWSI/NDPI: `data/images/original_wsi/<file_name>`
- patch画像: `data/patches/images/<wsi_stem>_<patch_id>.png`

初期MVPでは、ROI矩形または指定座標からpatchを作ります。patch幅と高さは別々に指定できるため、横長ROIは横長patchとしてアノテーション画面に渡せます。切り出し前にOpenSlideの `level`, `patch_x`, `patch_y` を調整しながらプレビューを確認できます。プレビューがほぼ白背景の場合は警告を出すため、座標やlevelを変えてからpatchを確定してください。

WSIビューアでは、マウスホイールでズーム、ドラッグで移動できます。赤枠が保存予定patchの範囲です。ビューア上に表示される `patch_x`, `patch_y`, `level` をコピーし、下の入力欄に貼り付けることで、指定した場所をpatchプレビューとして確認できます。

patch画像を学習画像として扱うため、YOLO座標はpatch内座標で正規化されます。`patch_width`, `patch_height`, `patch_level`, `patch_downsample`, `patch_level0_width`, `patch_level0_height` も保存され、patch内座標から親WSIのlevel 0座標へ戻せるようにしています。

WSI由来のannotationでは、patch内座標に加えて、親WSI上の座標も保存します。`patch_downsample` がある場合、`x_wsi = patch_x + x_in_patch * patch_downsample` として保存されます。

旧MVPのNDPI全体をOME-TIFFへ変換する補助関数は残していますが、通常のアノテーションではWSI patch workflowを使います。

### 自動patch queue

NDPI/WSIアップロード後の「自動patch queue」から、WSI全体を非重複tileへ分割し、組織を含むpatch候補を自動生成できます。

- `patch_size_px`: `1024` または `2048`
- `queue level`: OpenSlideの読み出しlevel
- `target_mpp`: 選択levelの推奨mppを初期表示
- `最小 tissue_ratio`: 空白背景を除外するための閾値

最初に低倍率thumbnailで明らかな空白tileを除外し、残った候補だけをOpenSlideから読み出して実patchの`tissue_ratio`を再計算します。巨大WSI全体をannotation canvasへ載せることはありません。

生成されたpatchは`data/patches/images/`へ保存され、queue状態は`data/patches/patch_manifest.csv`で管理されます。既存queueを同じ設定で再生成した場合、同じ`patch_id`のstatusとカウントは保持されます。

queue status:

- `not_started`: 未確認
- `in_progress`: 確認中
- `done`: アノテーション確認・保存済み
- `reviewed_empty`: 人間が好酸球0件と確認した陰性patch
- `skipped`: 今回は確認対象外
- `flagged`: 再確認が必要

アノテーション画像のすぐ下に、queue操作をまとめて表示します。

- `好酸球あり: 保存して次へ`: 現在のannotationを`done`として保存し、次のpatchへ移動
- `好酸球なし: 陰性保存して次へ`: `eosinophil`を0件として確認し、`reviewed_empty`で保存して次へ移動。`ignore`、`artifact`、その他細胞のannotationは保持
- `前のpatch` / `次のpatch`: 保存せずに前後移動
- `現在の内容を保存（移動しない）`: 保存後も現在のpatchに留まる
- `今回はスキップして次へ`: `skipped`にして次へ移動
- `要再確認にして次へ`: `flagged`にして次へ移動

手動ROI patch画面は初期状態では非表示です。「手動ROI patchを表示」トグルを有効にした場合だけ、WSIビューア、ROI選択、座標入力を表示します。通常作業では自動patch queueを使用してください。

WSI由来patchのアノテーション画面では、マウスホイールで表示を`100%`から`400%`まで拡大縮小できます。拡大後はキャンバス周囲のスクロールバーで表示位置を移動します。キャンバス下の`− / 100% / ＋`ボタンでも倍率を変更できます。このズームはブラウザ上の表示だけを変更し、annotationのpatch内座標、WSI座標、YOLO出力座標には影響しません。

`patch_manifest.csv`の主な列:

- `source_wsi_name`
- `patch_id`
- `patch_x`, `patch_y`
- `patch_width`, `patch_height`
- `target_mpp`
- `objective_magnification`
- `tissue_ratio`
- `status`
- `annotation_count`
- `eosinophil_count`

学習dataset生成時に「patch queueは done / reviewed_empty のみ」を有効にすると、queue管理されたpatchのうち、人間による確認が完了したpatchだけを出力します。`reviewed_empty`は「画像内の対象クラスである好酸球が0件」と人間が確認した陰性patchです。`ignore`は対象細胞ではなく、学習・評価から除外する領域または判定不能物として扱います。手動作成した従来patchはqueue statusがないため、既存の`reviewed / exported`条件で扱われます。

### CLAM-inspired patch prioritization

この機能はCLAM本体や深層学習によるWSI表現学習ではありません。CLAM導入前段階として、保存済みpatchから軽量なRGB/HSV特徴量を計算し、類似patchのクラスタリングと確認順の優先付けを行う機能です。torchや事前学習済みモデルは使用しません。

`patch_manifest.csv`には次の列が追加されます。古いmanifestを読み込んだ場合、不足列は空欄で自動補完されるため、既存queueとの後方互換性があります。

- `brightness_mean`: HSVの明度平均
- `saturation_mean`: HSVの彩度平均
- `hematoxylin_score`: 青紫色・暗色成分を用いたhematoxylin様スコア
- `eosin_score`: ピンク色成分を用いたeosin様スコア
- `nuclei_density_proxy`: 暗い青紫色pixelの割合による核密度proxy
- `red_orange_score`: 赤色・橙色成分の暫定スコア
- `cluster_id`: MiniBatchKMeansによるWSI内クラスタID
- `priority_score`: 組織率、核密度proxy、eosin、赤橙色スコアの重み付き暫定値
- `feature_version`: 特徴計算方式のバージョン。初期値は`rgb_hsv_v1`

自動patch queue画面ではcluster数を選択できます。新しいqueue生成時に特徴量とclusterを計算し、既存queueには「特徴量・クラスタを再計算」を使用できます。

queueの並び順:

- `優先度が高い順`: `priority_score`の降順
- `クラスタ順`: `cluster_id`ごとにまとめ、cluster内はpriority順
- `WSI上の位置順`: `patch_y`, `patch_x`順
- `組織率が高い順`: `tissue_ratio`の降順

`priority_score`は好酸球の確率ではなく、確認候補を並べるための暫定ヒューリスティックです。染色条件や臓器によって色特徴が変わるため、人間による確認を省略する目的では使用しません。

### Positive exploration mode

Patch review modeを`Positive exploration`へ切り替えると、好酸球陽性patchが少なく`reviewed_empty`が多いデータセットで、陽性候補を優先して確認できます。通常の`Standard review`と同じ`patch_manifest.csv`を使用しますが、表示順とナビゲーションだけを陽性探索向けに変更します。

デフォルトでは、現在のWSIに属し、学習除外されていない`not_started`、`in_progress`、`flagged`、`suspected_positive`を対象にします。`reviewed_empty`と`skipped`は除外し、`priority_score`が高い候補を先に表示します。priorityがないpatchでは`tissue_ratio`を補助的な並び順として使用します。

利用できるフィルタ:

- 未確認のみ、flaggedのみ
- reviewed_empty、done、skipped、学習除外patchの除外
- minimum priority score、top N candidates
- cluster ID、status
- tissue region、disease context、source organ

並び順:

- priority score降順
- tissue ratio降順
- cluster IDの後にpriority score
- WSI上の空間順
- random sample
- cluster-balanced

`cluster-balanced`では、clusterごとに指定した上位N枚を候補集合へ採用します。陽性patchが少ない場合、単純なpriority順だけでは似た色調・組織領域へ偏る可能性があるため、cluster-balanced samplingも併用してください。cluster IDがない場合はwarningを表示し、priority順へfallbackします。

陽性探索中の推奨運用:

- 好酸球なし: `reviewed_empty`
- 好酸球あり: eosinophil annotationを保存して`done`
- 好酸球らしいが迷う: `suspected_positive`
- 再確認が必要、別の問題がある: `flagged`
- 明らかなartifact: `skipped`または`exclude_from_training`

`flagged`は一般的な再確認対象、`suspected_positive`は陽性らしさを理由に再確認したいpatchとして使います。どちらも自動的に陽性labelになるわけではありません。

`reviewed_empty`が多いこと自体は異常ではありません。組織全体に対して好酸球が疎な場合、確認済み陰性patchが多数になるのは自然です。これらは陰性例として重要ですが、陽性探索時はデフォルトで候補から外します。

`exclude_from_training`は探索表示から除外でき、YOLO、CLAM-compatible export、MIL bag indexにも入りません。statusまたは除外設定を変更した後は、既存のCLAM export、deep feature、`mil_bags.csv`が古くなる可能性があるため、必要に応じて再生成してください。

将来的には、各patchの埋め込みベクトルをHDF5やNumPy形式で保存し、CLAM-compatible feature export、attention scoreのimport、cluster/attentionに基づくsamplingへ拡張する予定です。

### CLAM-compatible export

「CLAM-compatibleデータを生成」を押すと、現在のpatch queueと軽量patch featureを`data/clam/`へ書き出します。torchやCLAM本体は使用せず、後からCLAM/MIL用の深層特徴抽出へ進むためのCSV staging structureを作成します。

```text
data/clam/
├── patch_manifest.csv
├── slide_labels.csv
├── process_list_autogen.csv
├── coords/
│   └── <slide_stem>.csv
└── features/
    └── <slide_stem>.csv
```

- `patch_manifest.csv`: 全slideのpatch、座標、status、軽量特徴量、cluster、priority、WSIパスをまとめた表
- `coords/<slide>.csv`: slide単位のlevel 0座標、patchサイズ、level、downsample、target mpp
- `features/<slide>.csv`: 現在のRGB/HSV特徴量、cluster ID、priority score
- `slide_labels.csv`: `case_id`, `slide_id`, `label`, WSIパス、症例・臓器メタデータ
- `process_list_autogen.csv`: 後続のpatch/feature処理対象を管理するslide一覧

slide-level `label`には、保存済み画像メタデータの`disease_context`を使用します。`case_id`は`patient_id_hash`、`specimen_id`、`slide_id`の順で利用可能な値を採用します。学習前に、研究目的に合ったslide labelであることを必ず確認してください。

「patch queueは done / reviewed_empty のみ」が有効な場合、CLAM-compatible exportも人間が確認済みのpatchだけを対象にします。`reviewed_empty`は好酸球0件の確認済みpatchとしてMIL bagに含められます。

この`features/*.csv`はCLAMの深層埋め込みではありません。次段階では、`process_list_autogen.csv`と`coords/*.csv`を入力として、各patchをResNetなどのfeature encoderへ渡し、CLAMが利用するHDF5またはPyTorch feature filesを生成します。その後、`slide_labels.csv`を用いてslide-level MIL/CLAM学習へ接続します。

NDPI全体を巨大TIFFへ変換する必要はありません。元WSIとlevel 0座標を保持したまま、必要なpatchだけをOpenSlideから読み出す設計です。

#### CLAM exportの検証

1. 「CLAM-compatibleデータを生成」を押します。
2. 続けて「Validate CLAM export」を押します。
3. slide数、patch数、確認したCSVファイル数、status別件数を確認します。
4. slide別表の`patch_ids_match`がすべて`True`であることを確認します。
5. errorまたはwarningが表示された場合は、CLAM feature extractionへ進む前に内容を確認します。

バリデーションでは次を確認します。

- `patch_manifest.csv`, `slide_labels.csv`, `process_list_autogen.csv`の存在と必須列
- `coords/*.csv`, `features/*.csv`の存在と読み込み可否
- slideごとの`patch_id`がpatch manifest、coords、featuresで一致すること
- slide label、process list、patch manifestの`slide_id`集合が一致すること
- slide内で`patch_id`が重複していないこと
- `patch_count`がmanifestの実件数と一致すること
- patch数0のslideやCLAM export全体が空でないこと

`CLAM-compatible CSV stagingの整合性を確認しました`と表示されても、slide-level labelの医学的妥当性やtrain/validation分割のリークまでは検証しません。これらはMIL/CLAM学習前に別途確認してください。

#### Deep feature extraction

`scripts/extract_deep_features.py`は、CLAM/MIL学習へ渡す前段階として、`process_list_autogen.csv`で`process=1`になっているslideのpatch embeddingを生成します。Streamlitアプリ本体やCLAM本体のtrainingではありません。

PyTorch関連の依存は通常アプリから分離しています。ML用環境へ次を追加してください。

```bash
pip install -r requirements-ml.txt
```

ResNet18をCPUで実行する基本例:

```bash
python scripts/extract_deep_features.py --encoder resnet18 --device cpu
```

初回実行時はtorchvisionの事前学習済みweightsをダウンロードするため、インターネット接続が必要になる場合があります。既存出力は自動的にスキップします。再生成する場合は`--overwrite`を付けます。

```bash
python scripts/extract_deep_features.py --encoder resnet18 --device cpu --overwrite
```

主なオプション:

- `--encoder resnet18|resnet50`: feature encoderを選択
- `--device cpu|cuda|auto`: 実行deviceを選択
- `--batch-size 16`: 一度にencoderへ渡すpatch数
- `--no-pt`: `.pt`出力を作らずCSVだけ保存
- `--no-pretrained`: weights downloadを行わないpipeline動作確認用。学習用featureには使用しない

処理はNDPI/WSI全体をTIFFへ変換しません。`coords/<slide>.csv`のlevel 0座標`x`, `y`を使い、`patch_level`と`patch_width`, `patch_height`を指定してOpenSlideから必要領域だけを読み出します。読み出したRGB patchを224 x 224へresizeし、ResNetの最終分類層を除いたembeddingを保存します。

```text
data/clam/
├── deep_features_csv/
│   └── <slide_id>.csv
└── deep_features/
    └── <slide_id>.pt
```

CSVにはslide/patch ID、座標、patch size、level、target mpp、encoder情報と`feature_0`以降のembedding列が入ります。ResNet18は512次元、ResNet50は2048次元です。`.pt`にはfeature tensor、patch ID、座標、encoder情報をまとめて保存します。

この段階ではattention、slide-level分類、train/validation/test分割、CLAM trainingは実装していません。feature抽出前に「Validate CLAM export」でstaging CSVの整合性を確認し、slide labelと患者単位のデータ分割は研究者が別途確認してください。

#### Deep feature validation

深層特徴の生成後、patch stagingとの整合性を検証します。

```bash
python scripts/validate_deep_features.py
```

このスクリプトは`process=1`の各slideについて、次を確認します。

- patch manifest、coords CSV、deep feature CSVの`patch_id`集合
- coordsとfeatureのpatch数
- ResNet18の512次元、ResNet50の2048次元
- feature値の空欄、NaN、inf
- `feature_model`と`feature_version`
- `.pt`が存在する場合のtensor shape、patch ID数と順序

`.pt`は任意です。必須として検証する場合は`--require-pt`を付けます。不整合がある場合は終了コード1を返すため、後続処理や自動実行を停止できます。

```bash
python scripts/validate_deep_features.py --require-pt
```

#### MIL bag index

validation完了後、slide単位のfeature bag一覧を作成します。

```bash
python scripts/build_mil_bag_index.py
```

出力:

```text
data/clam/mil_bags.csv
```

`slide_labels.csv`を基準に、`process=1`かつdeep feature CSVが存在するslideだけを登録します。`.pt`がなくてもCSVがあればbagとして利用できます。`patch_count`はdeep feature CSVの実際の行数から計算します。

`mil_bags.csv`にはcase/slide ID、slide label、WSI名、患者・標本ID、feature CSV/PTのパス、patch数、encoder情報、確認・export日時を保存します。`label=unknown`はwarningになります。また、同じ`case_id`または`patient_id_hash`が複数slideに存在する場合、train/validation/test間の患者・症例リークを避けるためwarningを表示します。複数slideを持つ同一症例は、将来のsplit時に必ず同じpartitionへ配置してください。

推奨順序:

```bash
python scripts/extract_deep_features.py --encoder resnet18 --device cpu
python scripts/validate_deep_features.py
python scripts/build_mil_bag_index.py
```

ここで作成するのはMIL/CLAM学習に渡すbag indexまでです。attention計算、slide-level分類、CLAM training、データ分割はまだ実装していません。

#### アプリでのDeep feature / MIL bag確認

StreamlitアプリのCLAM/MILセクションにある「Deep feature / MIL bag status」では、既存成果物の状態だけを確認できます。アプリからfeatureの再計算やMIL trainingは行いません。

表示・確認する項目:

- `data/clam/mil_bags.csv`の有無とbag数
- slide ID、label、patch数、feature model/version
- feature CSVと任意の`.pt`ファイルの存在
- feature CSVの実際の行数と`mil_bags.csv`の`patch_count`の一致
- `--no-pretrained`で作成された`random` featureの警告
- JPAID由来の肝臓候補に見えるslideが`unknown`または`ECRS` labelになっている場合のmetadata確認警告

`.pt`が空欄でもfeature CSVがあればbagとして利用できます。ただし、学習コードが`.pt`を前提とする場合はdeep feature抽出を再実行してください。`random` featureはpipelineの動作確認専用であり、学習・解析には使用しません。

### Metadata修正・training除外・削除管理

アプリ上部の「学習データ管理」では、保存済みannotation JSONと`patch_manifest.csv`を参照して、slide/patchのmetadataを修正できます。画像をアップロードしていない状態でも利用できます。

Slide単位で編集できる項目:

- `project_template`, `disease_context`, `source_organ`
- `tissue_type`, `tissue_region`, `staining`
- `specimen_id`, `slide_id`, `patient_id_hash`, `notes`
- `exclude_from_training`, `exclusion_reason`

Patch単位で編集できる項目:

- `status`, `reviewed_at`
- `exclude_from_training`, `exclusion_reason`, `notes`

除外理由は`metadata_error`, `wrong_label`, `bad_patch`, `artifact`, `test_data`, `duplicate`, `other`から選択します。古いJSON/CSVに除外列がない場合は、`False`または空欄として読み込みます。

`exclude_from_training=true`のslide/patchは、YOLO training dataset、CLAM-compatible export、MIL bag indexから除外されます。一方、`dataset_manifest.csv`には除外フラグと理由を残すため、研究データの管理履歴を確認できます。

metadataや除外設定を変更すると、既存のCLAM export、deep feature、`mil_bags.csv`は古いmetadataに基づく可能性があります。画面のstale warningに従い、次の順で再生成してください。

```bash
# アプリでCLAM-compatible exportを再生成
python scripts/extract_deep_features.py --encoder resnet18 --device cpu --overwrite
python scripts/validate_deep_features.py
python scripts/build_mil_bag_index.py
```

管理画面から、選択slideのdeep feature CSV/PTと、再生成可能なCLAM CSV・`mil_bags.csv`を削除できます。元NDPI/WSIは削除しません。

Annotation JSONとpatch画像の物理削除は、確認チェックとpatch IDの再入力が必要です。物理削除は元に戻せないため、誤label、artifact、test dataなどは原則として`exclude_from_training`によるsoft deletionを使用してください。

#### Annotationの再読込とやり直し

保存済みpatchを再度開くと、アプリは`source_wsi_name + patch_id`を使って最新のannotation JSONを検索します。metadata修正によってexportファイル名が変わった場合でも、旧ファイル名に保存されたannotationを復元できます。

現在表示中のpatchで「保存済みannotationを再読み込み」を押すと、キャンバス上の未保存内容を破棄し、ディスク上の最新JSONからannotationとmetadataを読み直します。手動でアップロードしたannotation JSONはファイル内容のSHA-256で変更を判定するため、ファイル名やサイズが同じ修正版も再読込されます。

学習データ管理の「アノテーションを最初からやり直す」では、patch画像と元WSIを残したままannotationだけを空にし、patch statusを`not_started`へ戻します。実行前のJSONは次へ自動バックアップします。

```text
data/annotations/backups/
```

リセット後はannotation countとeosinophil countが0になり、review/export日時も空になります。既存のCLAM export、deep feature、MIL bagは古くなる可能性があるため、必要に応じて再生成してください。

#### Patch切替の高速化

WSI thumbnailと表示用patch画像はアプリ内でキャッシュし、Previous/Next操作では同じ巨大WSIのthumbnailを毎回作り直しません。通常は保存済み`data/patches/images/`のpatch画像を直接読み込みます。元WSIやpatch画像をアプリ外で置き換えた場合は、アプリを再起動してキャッシュを更新してください。

「学習データ管理」はトグルを開いた時だけ保存済みannotation JSONを走査します。通常のannotation中は閉じておくことで、patch切替時に全annotation JSONを読み直す待ち時間を避けられます。

### 日時・annotation履歴

研究データの作成・確認・export時刻は、Asia/TokyoのISO 8601形式で自動保存します。

```text
2026-06-10T17:30:00+09:00
```

`data/patches/patch_manifest.csv`:

- `created_at`: patch queueへ初めて登録された時刻
- `updated_at`: status、annotation count、feature、exportなどが最後に更新された時刻
- `reviewed_at`: `done`または`reviewed_empty`として人が確認した時刻
- `exported_at`: annotation、YOLO dataset、CLAM-compatible dataなどへ最後にexportされた時刻

`skipped`、`flagged`、`in_progress`へのstatus変更でも`updated_at`は更新されます。古いpatch manifestにこれらの列がない場合は、読み込み時に空欄で補完されます。`reviewed_empty`はannotation行が0件でも、`reviewed_at`により人間確認済みであることを追跡できます。

annotation JSON/CSV:

- `annotation_id`: annotationごとのUUID
- `annotation_created_at`: annotationを作成した時刻
- `annotation_updated_at`: annotationを最後に保存した時刻
- `annotation_session_id`: 同じアノテーション作業セッションを識別するID

既存annotationに`annotation_created_at`がない場合は、従来の`created_at`または保存時刻から補完します。再保存時には`annotation_id`と`annotation_created_at`を保持し、`annotation_updated_at`だけを現在時刻へ更新します。

`counts.csv`、`dataset_manifest.csv`、CLAM-compatibleのpatch manifest、coords、features、slide labels、process listにも`reviewed_at`と`exported_at`を含めます。

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

- `candidate_source`: `manual`, `imported_open_eoe`, `imported_cellpose`, `imported_custom_model`, `model_v1`
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

Open-EoE、Cellpose、自前モデルなどから候補を読み込む場合、未確認候補は原則として次の扱いにします。

```json
{
  "candidate_source": "imported_open_eoe",
  "annotation_status": "candidate_unconfirmed",
  "used_for_training": false
}
```

`rejected` のアノテーションは、`used_for_training=false` として扱います。YOLO export、将来のcrop export、training dataset exportでは、`used_for_training=true` のアノテーションだけを使います。これにより、human-confirmed annotationのみを学習用に使う方針を保てます。

## Candidate BBox Import

外部AIモデルが出力したbbox候補をCSVまたはJSONでimportできます。Open-EoEなど既存の好酸球検出モデルは、商用目的ではなく研究用の候補生成器として利用する想定です。商用利用や再配布を行う場合は、各モデル・重み・データセットのライセンスを必ず確認してください。

CellposeやOpen-EoEは必須依存には含めていません。このアプリは、それらのモデルを実行するのではなく、外部で生成済みのbbox候補を読み込むだけです。

CSV/JSONの必須項目:

- `source_model`
- `source_image_name`
- `label`
- `confidence`
- `x_in_patch` または `x_original`
- `y_in_patch` または `y_original`
- `bbox_width`
- `bbox_height`

任意項目:

- `patch_id`
- `patch_x`
- `patch_y`
- `x_wsi`
- `y_wsi`

importされた候補は、初期状態では `annotation_status=candidate_unconfirmed`, `used_for_training=false` です。未確認候補はYOLO export、crop export、training dataset exportには使いません。人間が確認して `confirmed_by_human` または `corrected_by_human` とし、`used_for_training=true` になったannotationだけを学習用に使います。

MVPでは、画面上の `Confirm all imported candidates` でimport候補を一括確認できます。個別候補ごとの承認・reject UIは今後の拡張予定です。

## YOLO変換

YOLO形式は次の形式で保存されます。

```text
class_id x_center_norm y_center_norm width_norm height_norm
```

座標は元画像サイズで正規化されます。patch画像の場合はpatch画像内で正規化されます。`ignore` ラベルは、UIのチェックボックスでYOLO出力から除外できます。既定では `Export used_for_training only` が有効で、YOLO出力には `used_for_training=true` のアノテーションのみが含まれます。

## YOLO学習用エクスポート

`Generate YOLO training dataset` を押すと、保存済みの画像別 annotation JSON からYOLO学習用ディレクトリを生成します。

```text
data/dataset/
├── images/
├── labels/
└── data.yaml
```

初期設定では `reviewed` または `exported` が付いた画像だけを対象にします。これは、完全手動で確認された human-confirmed annotation のみを学習用に使うためです。`ignore` ラベルは `Exclude ignore from YOLO export` により除外できます。各画像内では、既定で `used_for_training=true` のアノテーションのみがYOLO labelへ変換されます。

WSI patch workflowでは、YOLO学習画像は親NDPI/WSIではなく `data/patches/images/` に保存されたpatch画像です。YOLO座標はpatch画像内で正規化されます。親WSI上の座標は `metadata.csv` と `annotations.json` に保持されます。

現時点のMVPでは train / val / test の厳密な分割は行わず、同じ `images` ディレクトリを `data.yaml` の train / val / test に指定します。これは動作確認用の暫定仕様です。

評価用データセットを作る次段階では、同一患者・同一標本由来の画像がtrainとval/testにまたがらないように、`specimen_id` や `patient_id_hash` 単位で train / val / test を分ける必要があります。将来的には `dataset_manifest.csv` を使って分割を管理します。

## ディレクトリ構成

```text
.
├── app.py
├── requirements.txt
├── requirements-ml.txt
├── scripts
│   ├── extract_deep_features.py
│   ├── validate_deep_features.py
│   └── build_mil_bag_index.py
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
