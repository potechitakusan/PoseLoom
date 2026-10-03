# 標準テンプレートを使う

2026-10-02の実動作テストで、SaveImageAdvancedを使う標準テンプレートにも対応しました。最終画像保存ノードとしてSaveImage/SaveImageAdvancedを選べます。動的入力COMFY_AUTOGROW_V3のmin=0は画像なしを許可し、通常の必須入力とは区別して検証します。

ComfyUIの「テンプレート」で必要なモデル世代を検索し、そのローカル環境でノード・モデルが揃うテンプレートを選びます。UI形式（nodes/links/widgets_values）と、実行API形式（class_type/inputs）は別物です。最近のテンプレートはsubgraphも含むためwidget位置を推測する汎用変換はしません。

公式入口:

- https://github.com/Comfy-Org/workflow_templates/tree/main/templates
- https://docs.comfy.org/tutorials/image/qwen/qwen-image
- https://github.com/city96/ComfyUI-GGUF （必要な場合の量子化ローダー）

標準テンプレートを取得してエージェントが内容を確認できます。名前は公式一覧から選び、存在しない名前を推測しません。

```powershell
python -X utf8 scripts/environment.py template --name image_qwen_image --output output/templates/qwen_ui.json
```

revisionを指定しない場合はmainの現行ファイルです。取得時のSHA-256を記録し、再現時は `--revision COMMIT` を使います。ノード内 `properties.models` のURL・配置先は候補として説明し、利用者に取得方法を選んでもらいます。テンプレート取得はモデル自動取得を意味しません。

## 画像生成を既存バッチに接続

1. ローカルComfyUIでテンプレートを開く。使用する分岐だけ有効にし、モデル、CLIPデバイス、解像度、sampler/CFG等を合わせる。GGUFを選んだ場合は対応ローダーへ交換する。
2. API形式で保存する（UI設定の開発者向け保存機能。UI版で名称が違う場合は現在のメニューを確認）。エージェントにMCPやブラウザ操作があれば支援できる。接続ツールがない場合は利用者へこの一手順を説明する。
3. APIグラフを読み、positive prompt / seed / width / heightの実際のnode IDとinput名を確認する。モデルのloader input、steps、negativeは必要なら追加。値を推測しない。
4. slots JSONを作り、最終SaveImageのIDを指定して取り込む。例えば同梱のネイティブグラフなら `examples/generation_slots.example.json` を使える。標準UIテンプレートはIDが異なる。

```powershell
python -X utf8 scripts/workflow_template.py adapt --api output/native_api.json --slots examples/generation_slots.example.json --save-node 9 --output workflows/my_generate_api.json
```

SaveImageは内部契約のID 9へ正規化されます。ノードIDが衝突する場合もリンクを付け替えます。他のノード、リンク、sampler・CFG・scheduler・モデル世代の設定は保持します。parameter marker `${prompt}` 等は型を保って値へ差し替えます。

kit_config.jsonの `generation_workflow` を `workflows/my_generate_api.json` に設定します（設定ファイルからの相対パス）。UNet/CLIP/VAEをslotsへ入れた場合はqwen_unet/qwen_clip/qwen_vaeが渡ります。GGUFファイル名も文字列として使えます。省略したloader slotはテンプレート内の固定モデル名を保持します。1枚だけSaveImageへ出力するグラフを使います。

```powershell
python -X utf8 kit.py generate --prompt-file input/qwen21_pose_prompt.txt --width 512 --height 768 --output-dir output/check_template --prepare-only
python -X utf8 scripts/workflow_template.py validate --api output/check_template/generation_workflow_api.json
```

validateは `/object_info` と照合して未導入ノード・必須入力・未取得モデル・参照リンクを調べます。ComfyUIへジョブは送りません。型の全制約やGPUメモリまで保証しないので、1件生成で実動作を確認します。バッチの事前チェックにも同じ検証を使います。生成されたAPIは各出力フォルダへ残ります。

## Qwen画像編集とペア

文章生成用テンプレートと画像編集用テンプレートは独立です。generation_workflowを設定しても人物削除ワークフローは自動変換しません。既定の人物削除はQwen 2.1のTextEncodeQwenImage21を要求します。利用者が別世代を選ぶ場合、その世代の標準編集テンプレートをAPI形式で保存し、LoadImageのimageへ `${image}`、prompt/seed/steps等へmarkerを配置したJSONを `edit_workflow` に指定できます。最終SaveImageはID 8、prefixは `${prefix}`。resize用に `${resolution}`、重み用に `${unet}` / `${clip}` / `${vae}` も利用できます。実際の編集モデルが参照画像に対応することを1件で確認します。

画像編集なしでペアを作るときは、用意したペア画像と手動マスク2枚を `kit.py pair --image ... --masks ... ... --separation mask` に渡せます。DWPoseは完成後の人数確認にも使います。

## 同梱のAPI生成コード

generate_qwen21_pose.pyは既存Qwen 2.1運用を継承しています。潜在はEmptySD3LatentImage、CLIP deviceとタイルVAEを設定可能にしました。単純な標準ノード構成の例であり、全Qwen世代の推奨sampler設定を代用するものではありません。未指定時のCFG等は従来の値です。別モデルを使うならテンプレート自身の設定を保持した取り込み経路を優先します。
