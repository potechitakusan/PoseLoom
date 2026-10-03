# 配布前のローカル情報除去

公開用コピーからPCの絶対パスと画像の制作履歴を除去するプログラムをkitに含めています。原本・保守キャッシュ・移行ハッシュは変更しません。利用前に `python -m pip install -r requirements.txt` で依存関係を導入してください。

## 汎用の使い方

```powershell
python -X utf8 kit.py privacy clean --input output/to-publish --output output/clean-public --report output/privacy-clean-report.json
python -X utf8 kit.py privacy check --input output/clean-public --report output/privacy-check-report.json
```

単一ファイルにも使用できます。入力と出力は別の場所にし、出力とレポートには新しいパスを指定します。レポートは公開フォルダの外に置きます。`scripts/publication_privacy.py` の直接実行も可能です。`check` はZIPの中も検査します。ZIPの除去処理は、展開したファイルを `clean` してから新しいZIPを作る手順です。

|形式|処理|
|---|---|
|PNG|テキスト・EXIF・時刻チャンクを除去。画素の圧縮ストリームは保持|
|JPEG|EXIF/XMP・IPTC・コメントを除去。圧縮画素とICCプロファイルは保持|
|Blend|圧縮を展開し、保存されたファイル選択画面・取り込み元の弱参照・Textのローカルパスだけを同じ長さで消去して再圧縮。形状・姿勢・DNA・ポインタは保持|
|JSON|絶対パス文字列を置換。素材説明・ボーン情報・ライセンス本文は保持|
|その他|コピーした内容を検査。自動的な文字列置換は行わない|

Blendの対応はSDNAを読み取れる形式です。外部リソースの実参照や未対応フィールドの絶対パス、APIキーなどの既知パターンを検出した場合は中断します。必要なリソースを同梱・相対化し、キーは公開用入力から除去してから、新しい出力先でやり直してください。部分出力をそのまま公開しないでください。

ライセンスファイル・第三者NOTICE・公開活動名は削除対象にしません。検査はローカルパス、画像メタデータ、一般的な認証情報のパターンが対象です。画像に写った顔・文字、任意の氏名、独自形式の秘密情報は判別できないため、公開物の目視確認も必要です。成功結果は個人情報全般の不在を保証するものではありません。

## カタログとGitHub Releases

`kit.py catalog` は常に公開用のBlendとPNGを除去処理し、サイトと素材ZIPを検査します。`--verify` はリンクとハッシュの追加検証です。

```powershell
python -X utf8 kit.py catalog --plan examples/release_plan.example.json --output output/publish-next/site --release-dir output/publish-next/releases --records-dir output/publish-next/records --download-urls examples/download_urls.example.json --zip --verify
```

上記の例は設定を複製・編集して素材を用意してから実行します。作者の既存台帳では `maintenance/release_plan.json` と `maintenance/download_urls.json` を指定します。処理後のハッシュ・検査結果・抽出JSONはrecordsに保存し、公開サイトにはコピーしません。

素材ZIPにはAIやツールがモデルを探せるように次を収録します。

- `catalog.json`: そのZIPに実際に含まれる素材・画像・ハッシュ・説明JSONへの参照。
- `metadata/<collection>/<id>/asset.json`: 素材説明・出所・ライセンス。
- 同じ場所の `rig.json`: ボーン・制御・座標変換・単位・保存姿勢。
- 存在する素材の `body_preset.json`: 体形プリセット。
- HTMLガイド・画像・ライセンス・対象形式のBVHまたはBlend。

基本モデルZIPでは `metadata/<id>/` に同じ説明JSONを置き、モデルはZIP直下に配置します。JSONにある `path_base: "ZIP root"` のファイル・ライセンス参照はZIP直下が基準です。BVH版とBlend版のJSONは、その版に存在する形式だけを参照します。ZIP作成時に参照先とハッシュを照合します。Blend内の埋め込みJSONも保持します。

maintenanceとdistを丸ごと結合してZIPにはしません。指定コレクションの公開素材と、必要な説明JSON・ガイド・ライセンスだけを選んで構築します。原本のパス・キャッシュ・制作原稿・検証記録は公開対象外です。

GitHub Releasesへは検証済みreleasesのZIPを添付し、Cloudflareへはsiteだけを配置します。公開URLの設定とHTML更新手順は [html_updates.md](html_updates.md) を参照してください。
