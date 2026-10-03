# PoseLoom 制作エージェント

## 配布版の開始手順

最初の参考画像を用意する場合は、利用者に「imagegenで生成」「ComfyUIで生成」「手持ちの画像を使う」を選んでもらう。方法を指定済みなら再質問しない。imagegenを使える環境ではその画像生成機能を使い、ローカルQwenの導入を初期画像生成の必須条件にしない。imagegenが使えない環境ではその旨を説明して代替方法を選んでもらい、黙って別方式へ切り替えない。画像は新しい出力先へ保存し、生成方法・プロンプト・ファイルの出所を記録して既存のpose/pairへ渡す。詳細は `docs/setup.md` の「最初の参考画像の選択」。

最初に `docs/progress.md` と `README.md` を読む。導入は `docs/setup.md`、標準テンプレートは `docs/workflows.md`、670素材の保守は `docs/maintenance.md`、公開は `docs/hosting.md` を参照する。旧フォルダや作者の絶対パスへ依存した指示を作らない。

ComfyUI導入済みなら本体を入れ直さない。必要なノード・モデルを調べ、取得方法をコマンド実行/手動取得から選んでもらう。指定済みなら再質問しない。環境確認は `scripts/environment.py inspect`。既存ノードの無断更新を含めない。

12GBプロファイルはCPU CLIP・タイルVAE・逐次処理の開始設定で実機未検証。1件の生成・推論・Blender・書き出しを確認してから増やす。OOMを自動再試行しない。実object_infoとAPIグラフを照合し、モデル名やwidget位置を推測しない。

maintenance/assets/dist/releases/artifacts/output/tempはGit対象外だが作者の保守に必要。 `scripts/maintain.py check --migration-hashes` で確認する。cloneだけでは原本は揃わない。独自コードはMIT（LICENSE、適用範囲はLICENSE_STATUS.md）。公開URLは未確定。節目にdocs/progress.mdを更新する。

このフォルダが公開kitのルートです。distはCloudflare Pages専用、releasesはGitHub ReleasesのZIP専用で、どちらもGit対象外。実台帳はmaintenance/release_plan.json、公開URL設定はmaintenance/download_urls.json、制作原稿はmaintenance/input、配布記録はmaintenance/publicationへ保持し、GitとソースZIPから除外する。利用者向けの小さな設定例はexamplesに置く。公開サイトにZIP・保守用JSON・ソースZIPを混ぜない。

## 利用者からインストール方法を聞かれた場合

最初に `docs/setup.md` と `docs/install.html` を読む。利用者のOS、Blender、ComfyUIの有無に応じて必要な工程だけ案内する。Blender編集・書き出しにはComfyUIを要求しない。人物画像からの推定にはSAM 3D Body、ComfyUIでの文章からの参照画像生成には互換画像生成モデルが追加で必要。imagegenまたは手持ち画像を選んだ場合は初期画像用のQwen導入を省ける。外部モデル重み・ノード本体は同梱していない。外部ダウンロードはその提供元の利用条件を適用する。

## エントリーポイント

- `python -X utf8 kit.py --help`
- `python -X utf8 kit.py prepare-models`（基本モデルを新しく展開した場合）
- `python -X utf8 kit.py doctor --offline`
- `python -X utf8 kit.py pose --image <image> --model female --output-dir <new_directory>`
- `python -X utf8 kit.py retarget --fbx <matching_SAM3D_fbx> --model female --output <new.blend>`
- `python -X utf8 kit.py scene --spec <scene.json> --output <new.blend>`
- `python -X utf8 kit.py export --blend <saved.blend> --output-dir <new_directory> --id <id>`
- `python -X utf8 kit.py batch run --catalog <prompts.json> --output-dir <new_directory> --dry-run`
- `python -X utf8 kit.py catalog --plan <plan.json> --output <new_site> --release-dir <new_releases> --records-dir <new_records> --zip --verify`

`kit_config.example.json` を参考にローカルの `kit_config.json` を作る。別の場所にある設定には環境変数 `POSELOOM_CONFIG` を使う。設定ファイル内の相対asset_rootは、その設定ファイルの所在を基準にする。シーンJSONのパスはシーンJSON自身を基準に解決する。

## 素材の扱い

- 原本のblend、解析済みFBX、素材パッケージは上書きしない。生成物は新しい出力先へ保存する。
- 配布素材はBVHとBlendの2形式。Blend内のTextデータ `asset.json` と `rig.json` で素材・出所・ボーン情報を調べる。専用アドオンは不要。
- 基本男女モデルの `body_preset.json` もBlend内。prepare-modelsがsourcesへ取り出して制作工程に使う。
- カタログのexport_rootには書き出しキャッシュと検証用JSONを保持する。siteにはBVH/Blend・画像・HTML・ライセンスをコピーする。素材ZIPにはAI検索用のcatalog.jsonとasset.json/rig.json/体形JSONも収録し、maintenanceは丸ごと混ぜない。公開用コピーのパス・画像履歴除去はdocs/privacy.mdを参照する。
- 一括ZIPはコレクション別にBVH版とBlend版へ分ける。全素材をまとめたZIPは生成しない。公開HTMLには両形式のリンクを表示し、ZIP内のHTMLはdata-package-formatとCSSで対象外を非表示にする。対象外のhrefも外し、壊れたリンクを残さない。
- ZIP公開URLのキーはカテゴリID-bvh / カテゴリID-blend。examples/download_urls.example.jsonを参照する。
- 公開dist/search.htmlは全素材を検索し、コード順で初期50件、50/100/200件を選択できる。テーマ別ZIPのsearch.htmlは収録コレクションだけを対象とし、他コレクションへのリンクを含めない。
- ライブラリの保存姿勢を使用するときは、シーンJSONにblendを指定し、poseフィールドを省略する。
- 単体のCharacterコレクション追加と、複数人物のシーン取り込みを区別する。
- retargetは同じMHR体形プリセットで解析した元FBXが対象。配布はBVH/Blendだけだが、解析工程のFBXは内部の中間形式として必要。任意のBlendから書き出したFBXをこのretargetの入力として扱わない。
- バッチは各工程1回を既定とする。失敗・中断済みを勝手に再試行しない。再開契約のハッシュ不一致を黙って解除しない。
- 既存の参照画像を別バッチで3D化する場合は `batch import-sources` を使う。中断工程の再実行は利用者の明示指示に従い、旧状態を改変しない。
- 初回と未完了の途中では、要約JSONだけでなく実ファイル・ハッシュも確認する。
- 新規ポーズの目視選別の要否は利用者の指示に従う。ファイル検証と目視採否を混同しない。

## 配布と検証

人体データはMHR由来であることを保持する。ライセンスと変更通知を除かない。配布準備と外部公開は別の操作。独自コードはMIT。第三者由来のコード・素材は元の条件を保持する。公開先URLが未確定なら、その状態を記録して事実として伝える。

書き出しは保存した静止姿勢をベイクし、BVHに回転チャンネルを記録する。BVHはY上・cm、blendはZ上・m。Blender再読み込み検証と、CLIP STUDIO PAINT実機検証を区別する。

汎用コマンドを拡張し、案件固有の補正スクリプトをこのフォルダへ増殖させない。

