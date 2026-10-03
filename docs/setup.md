# 導入とダウンロードの選択

ComfyUI本体は導入済みとして扱います。エージェントは最初にOS、ComfyUIの実フォルダ、ComfyUIが使うPython、API URL、Blender、VRAM/RAM/空きディスク、必要な工程を確認します。portableならpython_embeded、venv版ならそのvenvのPythonです。制作ツールのvenvとComfyUIのPythonを混同しません。

## 必要な工程だけ用意する

### 最初の参考画像の選択

エージェントは最初の参考画像を用意する前に、次の方法から利用者に選んでもらいます。指定済みならその希望を使います。

|方法|進め方|
|---|---|
|imagegenで生成|エージェント環境の画像生成機能で参考画像を作り、新しい出力先へ保存。初期画像のためのローカルQwenは不要|
|ComfyUIで生成|標準テンプレートと利用者が選んだモデルを使う。ノード・モデルの自動/手動取得も選択可能|
|手持ち画像を使う|写真・イラスト・生成済み画像を入力にする。初期画像の生成モデルは不要|

imagegenはこのPython CLIに同梱した機能ではなく、エージェント側で利用できる画像生成機能です。利用できない場合は説明し、ComfyUIまたは利用者が別途用意した画像へ切り替えるかを選んでもらいます。黙って方式を変更しません。

参考画像は、全身・両手・両足が画面内に入り、姿勢や人物ごとの輪郭が読み取りやすい構図にします。生成方法、プロンプト、参照に使ったファイルなどの出所を画像とともに記録します。imagegenで作った画像も既存の画像入力経路へ渡せます。

```powershell
python -X utf8 kit.py pose --image output/reference01/reference.png --model female --output-dir output/pose01
python -X utf8 kit.py pair --image output/reference_pair/reference.png --output-dir output/pair01 --separation mask --masks person1_mask.png person2_mask.png
```

単体バッチの参照画像は `ID/source.png` の配置に揃えて `batch import-sources` で取り込めます。初期画像をimagegenで作っても、3D化にはSAM3DとBlenderが必要です。ペアの人物削除方式（qwen-remove）を選ぶ場合は、その後の画像編集用モデルが別途必要です。

|工程|必要なもの|
|---|---|
|保存済みBlendの編集・書き出し・サイト更新|Blender。サイト画像処理にはPillow|
|人物画像から3D化|基本モデル、SAM3Dノード・モデル、Blender|
|文章から参照画像を生成|imagegenを選ぶ場合はエージェントの画像生成機能。ComfyUIを選ぶ場合は互換画像生成モデル・ワークフローを追加|
|ペアの分離・検出確認|DWPose（controlnet_aux）。人物削除方式には画像編集モデルも追加。自動mask方式はSAM3_Detect対応ノードとSAM 3.1重みを別途要求し、手動マスクで省略可能|
|img2BVH比較|requirements-img2bvh.txtとMediaPipeモデル。主経路とは別|

制作ツールのPython環境（PowerShell例）:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
Copy-Item kit_config.example.json kit_config.json
```

既存設定があればコピーを省略します。requirements.txtは確認時の版を固定しています。新しいPythonへ無条件に同じ版を入れず、Python 3.12のvenvを使います。Blenderのみの操作にopencv等は不要です。

kit_config.jsonのblender_exe、comfy_root、comfy_url、asset_rootを実環境へ合わせます。環境変数POSELOOM_CONFIG / POSELOOM_BLENDER / POSELOOM_COMFY_ROOT / POSELOOM_COMFY_URL / POSELOOM_ASSET_ROOTでも指定可能。相対パスは設定ファイルの場所を基準に解決します。

```powershell
python -X utf8 scripts/environment.py inspect
python -X utf8 kit.py doctor --offline
```

## ノード取得: ユーザーが方法を選ぶ

エージェントは工程に必要なノードだけを示し、「コマンドで取得・導入」「リンクから自分で取得」の希望を尋ねます。どちらかをすでに指定されたら再質問しません。外部環境への書き込みは実行環境の権限に従います。

SAM3D: https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills

DWPose: https://github.com/Fannovel16/comfyui_controlnet_aux

GGUF（量子化モデルを選ぶ場合のみ）: https://github.com/city96/ComfyUI-GGUF

手動の配置先を表示するだけ:

```powershell
python -X utf8 scripts/environment.py node sam3d --mode manual
python -X utf8 scripts/environment.py node dwpose --mode manual
```

自動でcloneと依存関係を導入する例（COMFY_PYTHONは利用者の実パスへ置換）:

```powershell
python -X utf8 scripts/environment.py node sam3d --mode automatic --comfy-python COMFY_PYTHON
python -X utf8 scripts/environment.py node dwpose --mode automatic --comfy-python COMFY_PYTHON
```

gitがPATHに必要です。既存ノードは上書き・更新しません。対応版を選ぶには `--revision COMMIT_OR_TAG`。SAM3Dの確認版は `licenses/provenance.json` に記録。既定は現行上流のため同じ版になる保証はなく、導入後に `/object_info` で実ノードを照合します。SAM3Dは隔離ワーカーも構築するため処理時間・ディスク容量が必要です。既存ジョブの終了後、利用者の起動方法でComfyUIを再起動します。

## モデル取得: ユーザーが方法を選ぶ

モデル名だけからURLを推測しません。標準テンプレートのモデル情報、公式README、実際の `/object_info` ローダー一覧を確認して、モデルの世代、量子化方式、ライセンス、容量、配置先を提示します。Qwen 2.1と旧Qwenのテキストエンコーダーは交換可能と仮定しません。

SAM3Dの現行READMEには初回起動時のモデル自動取得があります。手動派の利用者には、起動前にREADMEとノード実装で対象ファイル・配置先・自動取得挙動を確認して説明します。第三者ノード自身が行うダウンロードまで本ヘルパーが止めることはできません。DWPoseも初回実行時の検出モデル取得に注意します。

一般のモデルについて、HTTPSの実ダウンロードURLを選んだ後:

```powershell
python -X utf8 scripts/environment.py model --mode manual --url MODEL_HTTPS_URL --directory vae --filename MODEL_FILENAME
python -X utf8 scripts/environment.py model --mode automatic --url MODEL_HTTPS_URL --directory vae --filename MODEL_FILENAME --sha256 EXPECTED_SHA256
```

manualはURL・配置先を表示します。automaticはストリームで `.part` へ保存、指定ハッシュを検証してから正式名にします。ハッシュが提供されない場合は `--sha256` を省略し、取得後のハッシュを記録します。中断ファイルは保持し、既存ファイルの上書きや自動再試行はしません。ログインが必要なモデルは提供元UI/公式CLIで取得してください。トークンを公開設定へ書きません。

基本モデルは公開する `poseloom-base-models.zip` を `assets/models` へ展開します。直下に `male.blend` と `female_anime_v2.blend` を置きます。公開URLはまだ未設定です。今回の作者向け移行コピーには基本モデルが入っています。

```powershell
python -X utf8 kit.py prepare-models
python -X utf8 kit.py doctor
python -X utf8 kit.py pose --image reference.png --model female --output-dir output/first_pose
```

doctorは現状の一覧です。ready_poseにはDWPose確認も含まれますが、単独のposeコマンド自身はDWPoseを呼びません。ノード欠落の表示を工程別に判断してください。

## VRAM 12GBで始める

`kit_config.12gb.example.json` はCLIPのCPU処理とタイルVAEデコードを有効にします。既存kit_config.jsonへ必要な項目だけ移し、モデル名は選択した互換モデルへ合わせます。ComfyUIを低VRAM設定で起動する場合は、既存ランチャーの引数へ `--lowvram` を加える選択肢があります。再起動前に他のジョブを確認し、エージェントが勝手に終了させません。

まず単独画像・512×768・batch_size=1で開始します。Qwenの標準大型重みを12GBへ全部常駐させる前提にはしません。CPU/RAMオフロードを使い、必要ならGGUF等のより小さい対応重みとローダーを選択して標準テンプレートを調整します。Qwen経路ではRAM 64GBを推奨する運用目安とし、十分なページファイル・空きディスクも確認します。モデルファイルサイズはVRAM必要量そのものではありません。

```powershell
python -X utf8 kit.py generate --prompt-file input/qwen21_pose_prompt.txt --width 512 --height 768 --output-dir output/reference_small --prepare-only
```

API検証後にprepare-onlyを外して1件生成→その画像でpose→Blender保存/再読込→BVH/Blend書き出しを確認します。QwenとSAM3Dを並行実行せず、SAM3Dの前に既存の `/free` 処理で生成モデルを解放します。OOMならそこで停止し、モデル・解像度・オフロードを見直します。ペア生成は `kit.py pair --width 768 --height 768`、画像編集は `--edit-resolution` で別途調整できます。

12GB実機の完走を本パッケージの検証済み事項として説明しないでください。CPUオフロードで所要時間も変わります。画像生成が難しい環境でも、利用者が用意した画像から3D化する経路を提示します。量子化やモデル変更で既存の参照画像とピクセル一致する保証はありません。
