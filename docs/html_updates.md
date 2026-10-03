# Cloudflare用HTMLの更新手順

この手順は公開kitにも含まれます。配布先を問わない汎用手順と、GitHub Releasesを使う場合の手順を説明します。サイト構築には書き出し済みの素材とキャッシュが必要です。kitを取得しただけでは既存670素材を再構築できません。初めて使う場合は自分の素材を書き出し、設定例から台帳を用意します。

## 変更元を編集する

distは生成結果です。継続的な変更は次の変更元へ反映してから再構築します。生成済みHTMLだけを編集すると、次の構築で変更が消えます。

|変更したい内容|変更元|
|---|---|
|カテゴリ名・説明・分類・素材名|使用する台帳JSONのcollections / assets|
|ZIPのダウンロード先|使用するURL設定JSON。キーはコレクションID-bvh / コレクションID-blend|
|共通ヘッダー・ナビゲーション・フッター|scripts/build_catalog.pyのpage()|
|トップの見出し・紹介文・カテゴリ一覧|同ファイルのbuild()内のheroとカテゴリページ生成部分|
|FAQ・使い方・利用規約の説明|同ファイルのfaq_section() / howto() / license_page()|
|検索ページの表示と動作|同ファイルのsearch_page()|
|色・余白・フォント・レスポンシブ表示|同ファイルのCSS|

台帳のtitleはカタログJSONのタイトルです。HTMLのブランド名やトップの見出しはテンプレート側を編集します。説明文を変更するときも第三者ライセンス・NOTICE・出所は保持します。

## 配布先を問わない汎用手順

1. 台帳とURL設定を用意します。初回の例は下記です。既存ファイルがある場合はそれを使い、上書きしません。台帳のsource・preview・export_root・license_sourceは台帳自身の所在を基準とする相対パスです。例の素材は自分で制作・書き出してから使います。

   ```powershell
   New-Item -ItemType Directory -Path maintenance -Force
   Copy-Item examples/release_plan.example.json maintenance/my_release_plan.json
   Copy-Item examples/download_urls.example.json maintenance/my_download_urls.json
   ```

2. 変更元を編集し、新しい出力先にサイトとZIPを構築します。フォルダ名は例で、次回はsite-update-02など未使用の名前へ変更します。既存出力先はコマンドが拒否します。

   ```powershell
   python -X utf8 kit.py catalog --plan maintenance/my_release_plan.json --download-urls maintenance/my_download_urls.json --output output/site-update-01/site --release-dir output/site-update-01/releases --records-dir output/site-update-01/records --zip --verify
   ```

3. コマンドが正常終了し、records/verification.jsonのerrorsが空であることを確認します。site/index.htmlとsite/search.htmlをブラウザで開き、文言・レイアウト・検索・個別BVH/Blendリンクを確認します。検証は外部HTTPSリンクの到達性を確認しないため、ZIPリンクは別途ブラウザで確認します。
4. ZIPを選んだ配布先へ公開し、実際のHTTPS URLをURL設定JSONへ記入します。未公開のキーはnullにします。配布先のホスト名をHTMLテンプレートへ直接埋め込む必要はありません。URL設定からHTMLへ反映されます。
5. URLだけを変更した場合はZIPを再生成せず、新しい出力先でサイトを再構築します。HTMLテンプレートや素材も変更した場合は手順2から新しい配布版を作ります。

   ```powershell
   python -X utf8 kit.py catalog --plan maintenance/my_release_plan.json --download-urls maintenance/my_download_urls.json --output output/site-update-02/site --records-dir output/site-update-02/records --verify
   ```

6. 最終版のサイトをCloudflare Pagesへ配置します。Node.js/npmとWranglerの利用環境を用意し、初回はログインとPagesプロジェクトを作成します。プロジェクト名と本番ブランチ名は自分の設定に置き換えます。

   ```powershell
   npx wrangler login
   npx wrangler pages project create YOUR_PROJECT
   npx wrangler pages deploy output/site-update-02/site --project-name YOUR_PROJECT --branch YOUR_PRODUCTION_BRANCH
   ```

   既存プロジェクトの更新ではdeployだけを実行します。配置するのはsiteフォルダ全体です。削除済み素材や古いHTMLを残さないよう、前のサイトへの差分コピーではなく検証したサイト一式を使います。ローカルの採用版をdistへ保存する場合も同じ方針で入れ替え、旧版は公開フォルダの外へ保持します。

7. 公開サイトでトップ・検索・個別素材・ZIPダウンロードを確認します。HTML・CSS・画像・個別BVH/Blend・素材ライセンスは保持し、ZIP・保守用JSON・kitソースZIPはサイトへ混ぜません。

配置方法は[Cloudflare Direct Uploadの公式手順](https://developers.cloudflare.com/pages/get-started/direct-upload/)を参照してください。

## GitHub ReleasesでZIPを配布する場合

汎用手順のZIP公開とURL設定を次の順序で行います。

1. 新しい版のReleaseを作り、手順2のreleasesフォルダ内のコレクション別BVH/Blend ZIPを添付します。基本モデルZIPが生成されている場合はそれも添付します。ZIPはGitへ登録せずReleaseの添付ファイルにします。
2. Releaseを公開してから、各添付ファイルのダウンロードURLを取得します。添付名と台帳のcollection IDが対応していることを確認します。バージョン固定のURLは次の形です。OWNER・REPOSITORY・TAGは自分の値に置き換え、実際の添付リンクをコピーして使います。

   ```text
   https://github.com/OWNER/REPOSITORY/releases/download/TAG/poseloom-my_poses-bvh.zip
   https://github.com/OWNER/REPOSITORY/releases/download/TAG/poseloom-my_poses-blend.zip
   ```

3. URL設定JSONの対応するキーへ記入します。以下は説明用の例なので、そのまま公開設定として使わないでください。

   ```json
   {
     "my_poses-bvh": "https://github.com/OWNER/REPOSITORY/releases/download/TAG/poseloom-my_poses-bvh.zip",
     "my_poses-blend": "https://github.com/OWNER/REPOSITORY/releases/download/TAG/poseloom-my_poses-blend.zip"
   }
   ```

   基本モデルを配布する場合はbase-modelsキーに実際のposeloom-base-models.zipのURLも追加します。releases/tag/TAGというRelease紹介ページではなくZIP添付ファイルのURLを設定します。公開状態とダウンロードをログインしていないブラウザでも確認します。リンク形式は[GitHubの公式説明](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases)を参照してください。

4. 汎用手順5でサイトを再構築・検証し、手順6でCloudflareへ配置します。順序は「ZIP公開 → 実URL設定 → HTML再構築 → Cloudflare更新」です。旧版サイトが参照するRelease添付は、そのリンクを使うサイトを更新するまで保持します。

## このリポジトリの既存670素材を更新する場合

台帳をmaintenance/release_plan.json、URL設定をmaintenance/download_urls.jsonに置き換えます。構築前にpython -X utf8 scripts/maintain.py check --migration-hashesを実行します。実台帳と原本は公開kitに含まれません。

## HTMLの変更をkitにも反映する

scripts/build_catalog.pyとこの文書は公開kitの一部です。変更後は新しい保存先でソースZIPを作り、manifestを更新して検証します。保存先が既にある場合は別の版名に変更します。

```powershell
python -X utf8 scripts/package_source.py --output releases/site-update-01/poseloom-agents-source.zip
python -X utf8 kit.py verify
```

必要に応じてこの新しいソースZIPもGitHub Releaseへ添付します。Cloudflareへ送るのはサイトだけです。
