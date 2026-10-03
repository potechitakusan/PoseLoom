# Cloudflare PagesとGitHub Releasesへの公開

HTMLの変更元と再構築・検証・配置の順序は[Cloudflare用HTMLの更新手順](html_updates.md)を参照してください。汎用手順とGitHub Releasesの場合を説明し、公開kitにも収録しています。

公開用コピーの情報除去とAI検索用のZIP内JSONは[配布前のローカル情報除去](privacy.md)を参照してください。catalogは除去・検査を自動実行し、保守用原本を保持します。

|場所|用途|配布先|
|---|---|---|
|dist/|HTML・CSS・画像・個別BVH/Blend・素材ライセンス|Cloudflare Pages|
|releases/|テーマ別BVH/Blend・基本モデル・kitソースのZIP|GitHub Releases|
|maintenance/publication/|カタログJSON・ダウンロード台帳・検証結果|非公開|
|maintenance/release_plan.json|既存670素材の実台帳|非公開|
|maintenance/download_urls.json|実際のRelease添付URL|ローカル設定。サイトに反映|

すべての生成物とmaintenanceはGit対象外です。公開kitには汎用コード・説明・設定例・初期プロンプト・ライセンスを含めます。

## 新しい配布版の構築

```powershell
python -X utf8 scripts/maintain.py check --migration-hashes
python -X utf8 kit.py catalog --plan maintenance/release_plan.json --output output/publish-next/site --release-dir output/publish-next/releases --records-dir output/publish-next/records --download-urls maintenance/download_urls.json --zip --verify
```

検証後にsiteをdist、ZIPをreleases、recordsをmaintenance/publicationへ採用します。既存の出力先は拒否するため、版ごとに新しい出力先を指定します。初回利用者はexamples/release_plan.example.jsonとexamples/download_urls.example.jsonを複製して設定します。

## GitHub Releases

releases内のZIPをReleaseの添付ファイルとしてアップロードします。ZIPをGitへ登録しません。コレクション別にBVH版とBlend版を分け、基本モデルとkitソースも個別ZIPにします。

実際の添付HTTPS URLをmaintenance/download_urls.jsonへ設定します。キーはコレクションID-bvh / コレクションID-blend、およびbase-modelsです。未設定はnullで、架空のリンクは生成しません。

```powershell
python -X utf8 scripts/package_source.py --output output/publish-next/releases/poseloom-agents-source.zip
python -X utf8 kit.py verify
```

ソースZIPには実台帳・制作原稿・保守記録・PC設定・外部モデル重みを含めません。--outputを省略するとreleases/poseloom-agents-source.zipへ新規作成します。既存ZIPは上書きしません。

## Cloudflare Pages

### Wrangler CLIの導入とログイン

Node.jsとnpmを用意し、このリポジトリのルートで実行します。ツール本体はGit対象外のmaintenanceに導入し、kitソースや公開サイトには同梱しません。

```powershell
npm install --prefix maintenance/tools/cloudflare wrangler --no-audit --no-fund
$wrangler = ".\maintenance\tools\cloudflare\node_modules\.bin\wrangler.cmd"
& $wrangler --version
& $wrangler login
```

loginで開くブラウザからCloudflareアカウントを認証します。macOS/Linuxでは `.cmd` を外して実行してください。

ブラウザのDirect Uploadは1,000ファイルまで、Wranglerは20,000ファイルまでです。両方とも1ファイル25 MiBが上限です。現在のdistは2,248ファイルで、Wranglerの範囲内です。上限と手順は[Cloudflare公式Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)を参照してください。

### サイトのアップロード

Releaseの実URLを設定してサイトを再構築・検証した後、distフォルダ全体を公開します。distが公開ルートです。ZIP・保守用JSON・ソースZIP・ローカルのZIP一覧ページを混ぜません。個別BVH/Blend・画像・素材ライセンスはサイトに必要なので保持します。

```powershell
& $wrangler pages deploy dist --project-name YOUR_PROJECT
```

YOUR_PROJECTはCloudflare Pages上の実際のプロジェクト名に置き換えます。既存プロジェクトがある場合はその名前を使います。新規作成には `& $wrangler pages project create` を使用できます。loginと導入だけではサイトは公開されません。deployは外部公開の操作です。

公開URLは未設定です。GitHub ReleasesへのアップロードとCloudflareへの配置は未実施です。

