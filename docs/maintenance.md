# 制作と配布物の保守

このPoseLoomフォルダが公開kitのルートです。実台帳はmaintenance/release_plan.json、公開URL設定はmaintenance/download_urls.json、制作原稿はmaintenance/inputに保持します。これらはGitとソースZIPから除外します。台帳のパスは台帳自身の所在を基準に解決します。

## 既存670素材の確認と再構築

```powershell
python -X utf8 scripts/maintain.py check --migration-hashes
python -X utf8 kit.py catalog --plan maintenance/release_plan.json --output output/dist-next/site --release-dir output/dist-next/releases --records-dir output/dist-next/records --download-urls maintenance/download_urls.json --zip --verify
```

新しい出力先で検証し、サイトをdist、ZIPをreleases、記録をmaintenance/publicationへ採用します。distはCloudflare Pages専用、releasesはGitHub Releases専用です。原本や完成済みZIPは上書きしません。

catalogは公開用コピーからローカルパスと画像履歴を除去します。単独の除去・検査には `kit.py privacy clean/check` を使います。対象形式・注意点・ZIP内のAI検索用JSONは[privacy.md](privacy.md)を参照してください。

## 制作と追加

```powershell
python -X utf8 kit.py pose --image reference.png --model female --output-dir output/pose01
python -X utf8 kit.py open output/pose01/posed.blend
python -X utf8 kit.py export --blend output/pose01/posed.blend --output-dir maintenance/exports/my_poses/P001 --id P001
python -X utf8 kit.py batch run --catalog examples/batch.example.json --output-dir output/additions --dry-run
```

新しいバッチはexamples/batch.example.jsonを複製し、library_id・ID・seed・prompt・candidate_countを変更します。12GBは実機未検証なので1件から確認します。既存の作者向けテーマ原稿はmaintenance/inputに保持します。人物入り参照画像があればbatch import-sourcesを使います。失敗・中断の自動再試行と契約ハッシュの無断解除はしません。

台帳の必須項目はexamples/release_plan.example.jsonを参照してください。sourceは元Blend、previewは撮影PNG、collectionは台帳のカテゴリIDです。解析元FBXは配布Blendから再出力したFBXで代用しません。背景へ保存姿勢を配置する場合はexamples/scene.jsonでblendを指定しposeを省略します。

```powershell
python -X utf8 scripts/maintain.py jobs --plan maintenance/release_plan.json --ids P001 --output output/export_jobs.json
blender -b --python-exit-code 1 -P scripts/blender/export_asset.py -- --jobs output/export_jobs.json
```

変更したIDだけ書き出します。BVHはY上・cm、BlendはZ上・mです。ファイル検証と目視採否を区別します。CSP実機適用は未検証です。

## バックアップと公開kit

作者はこのフォルダ全体をバックアップし、別の場所でcheck --migration-hashesを確認してください。Git対象外のmaintenance・assets・dist・releases・outputには復元に必要なデータがあります。GitHubのcloneだけでは既存素材の原本を復元できません。移行ハッシュや完了印を保持し、古いキャッシュの出所表記を書き換えません。

python -X utf8 scripts/package_source.pyでreleases/poseloom-agents-source.zipを新規作成し、kit.py verifyで検証します。既存ZIPがある場合は--outputで新しい版の保存先を指定します。モデル・maintenance・PC設定・dist・releases・artifacts・output・tempは公開ソースに含めません。公開先ごとの操作はhosting.mdを参照してください。
