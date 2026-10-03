# PoseLoom 制作エージェント

**簡単な使い方：チェックアウトしたこのフォルダをCodexで開き、あとは使い方をCodexに聞いてください。**

まず「AGENTS.mdを読んで、導入と使い方を教えてください」と伝えてください。作りたいものや利用環境を説明し、導入・操作は生成AIと相談しながら進められます。Codex以外のAIコーディングエージェントでも、AGENTS.mdを読ませてから相談できます。

ComfyUI導入済みのPCで、人物画像から編集可能な3Dポーズを作り、BVH / Blendの無料配布サイトを保守するためのコードです。Blenderだけで編集・書き出し・サイト構築もできます。

最初の参考画像は **imagegenで生成／ComfyUIで生成／手持ち画像を使う** から選べます。imagegenを選んだ場合は、エージェント側の画像生成機能で作った画像を既存の3D化工程へ渡します。

エージェントに次のように依頼してください。

> AGENTS.mdを読んで導入を手伝ってください。ComfyUIは導入済み、NVIDIA VRAM 12GBです。ノード・モデルの取得は、コマンドで任せるものと自分でダウンロードするものを選びたいです。

> 画像からポーズを作ってください。完成したBlendを確認してから配布台帳へ追加し、新しいdistを構築してください。

> ComfyUIの標準テンプレートから画像生成ワークフローを作り、この制作ツールで使えるようにしてください。

- [導入とダウンロードの選択](docs/setup.md)
- [標準テンプレートとAPI連携](docs/workflows.md)
- [制作・追加・保守・移行](docs/maintenance.md)
- [Cloudflare Pages / GitHub Releasesへの公開](docs/hosting.md)
- [公開HTMLの書き換え・再構築（汎用／GitHub Releases）](docs/html_updates.md)
- [公開用コピーのローカル情報除去・ZIP内JSON](docs/privacy.md)
- [現状・検証範囲](docs/progress.md)

入口は `kit.py`。Python 3.12、Blender 4.3で確認しています。ComfyUIノード・モデル重みは同梱しません。VRAM 12GBではCPUオフロード・量子化・分割デコード・逐次処理で小さい1件から確認します。12GB実機での完走は未検証です。既存画像を使えばQwenの導入を省けます。

このPoseLoomフォルダが公開kitのルートです。GitHubのソース、GitHub ReleasesのZIP、Cloudflare Pagesのサイト、非公開の保守データを分けています。

|場所|役割|GitHubのGit対象|
|---|---|---|
|kit.py / scripts / docs / input / examples / licenses|汎用CLI・説明・初期プロンプト・小さな設定例・第三者表示|対象|
|skills/poseloom|任意のエージェントスキル|対象|
|manifest.json / requirements*.txt / kit_config*.example.json / README / AGENTS.md / LICENSE* / .gitignore|kitの検証・依存関係・設定例・利用案内|対象|
|kit_config.json|このPCのパス設定|対象外|
|assets/models|基本男女モデル・体形プリセット|対象外。基本モデルZIPで配布|
|maintenance|原本・キャッシュ・実台帳・公開URL設定・制作原稿・検証記録|対象外。作者の保守用|
|dist|HTML・CSS・画像・個別BVH/Blend・素材ライセンス|対象外。Cloudflare Pagesへ|
|releases|テーマ別BVH/Blend・基本モデル・kitソースのZIP|対象外。GitHub Releasesへ|
|artifacts / output / temp|過去のパッケージ・生成物・一時出力|対象外|

GitHubからソースだけ取得した利用者は、基本モデルZIPを別途展開して新しい素材を制作できます。作者が既存670素材を保守するには `maintenance` も保持してください。GitHubのcloneだけでは既存素材の原本は復元できません。

実台帳は `maintenance/release_plan.json`、公開URL設定は `maintenance/download_urls.json` に保持します。利用者には `examples/release_plan.example.json`、`examples/download_urls.example.json`、`examples/batch.example.json` を公開します。

ソースZIPは `python -X utf8 scripts/package_source.py` で `releases/poseloom-agents-source.zip` に新規作成し、`python -X utf8 kit.py verify` で照合します。既存ZIPがある場合は `--output` で新しい版の出力先を指定します。

独自コードは [MITライセンス](LICENSE)。適用範囲は [LICENSE_STATUS.md](LICENSE_STATUS.md)。第三者由来の条件・NOTICEは `licenses/` に保持します。


