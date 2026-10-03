# 制作エージェントの状態

## 2026-10-03 独自コードのMITライセンス採用

- 作者の指定により、独自制作コードと付随する独自文書・設定例にMITを採用。agents_dist/LICENSEに全文を追加し、著作権表示を2026 PoseLoom contributorsとした。
- LICENSE_STATUS.mdに適用範囲を明記。第三者コード・モデル重み・基本モデル・BVH/Blend・参照画像は一括適用の対象外とし、元のライセンス・NOTICEを保持。
- README、運用ガイド、保守文書を更新。配布ソースZIPを再作成し、CRCと全収録ファイルのハッシュを検証。kit.py verifyでも変更・欠落0を確認。

最終更新: 2026-10-03

追記: 最初の参考画像をimagegen/ComfyUI/手持ち画像から利用者が選ぶ運用を追加。imagegenはエージェント側の機能として使い、保存画像を既存pose/pair/import-sourcesへ渡す。利用できない場合の説明、初期Qwen要件の省略、後続の人物削除用モデルとの区別を文書化。ソースZIPを更新してハッシュ確認。

producerのCLI・Blender処理・第三者ライセンス・原稿を独立ルートへ移行。公開670素材の元Blend/PNG/キャッシュ4793ファイル、7,003,343,070 bytesをコピーしハッシュ一致確認。現在のdistと基本モデルも保持。台帳を新ルート相対パスへ変更し旧asset_presetsを削除。

ノード/モデルの自動・手動取得、環境一覧、公式テンプレート取得、API取り込み、静的検証、保守jobs、ソースZIP作成を追加。12GB設定例はCPU CLIP・タイルVAE。latentをEmptySD3LatentImageへ修正し、ペア解像度を指定可能にした。

検証結果はmaintenance/reports/validation.jsonを参照。670素材のサイト2248ファイル・2113ハッシュ・4479リンクはエラー0。テーマ別/基本モデルの全15 ZIPを構築し、CRC・形式分離・内部リンク検証を通過。空白を含む独立フォルダでも素材1件の再構築成功。ソースZIPの別フォルダ展開・全ファイル照合成功。標準テンプレート取得、APIのID衝突処理・型を保つ差し替え・不正UI入力拒否、Blenderでの体形抽出も確認。

2026-10-02にComfyUIを起動し、独立展開したエージェントで初期画像3分岐×3枚の9体を3D化。実ノード照合、全体のIK編集・BVH再読み込み・テーマ別6 ZIP・制御10ケースを通過。SaveImageAdvanced対応と任意動的入力の検証を修正。詳細はmaintenance/reports/branch_tests.md。未完了: 12GB実機推論、公開URL、Cloudflare/GitHub公開、CSP実機適用。16GB環境の結果を12GB保証として扱わない。

次の制作は新しいoutputへ保存し、台帳追加→対象ID書き出し→新しいdist構築→検証。旧フォルダは削除していない。


2026-10-03: プロジェクト名をImg23DBodyからPoseLoomへ変更。環境変数はPOSELOOM_*、スキルはskills/poseloom、ZIPはposeloom-*.zip。maintenance/のexportキャッシュ、PNGメタデータ、Blend内の埋め込みasset.jsonは完了印のハッシュ保持のため旧名のまま。次回の再書き出しで更新する。

## 2026-10-03 公開先と保守データの分離

- 15素材ZIPをdist/downloadsからreleasesへ移動。dist/siteの公開ファイルをdist直下へ移し、Cloudflare Pagesの公開ルートをdistに統一。重複ソースZIPを削除し、ローカル一覧HTMLとJSON記録はmaintenance/publicationへ退避。
- 実台帳・公開URL設定をmaintenance、制作原稿をmaintenance/input、実機検証記録をmaintenance/reportsへ移動。台帳の相対パスを補正。原本・キャッシュ・移行ハッシュは保持。
- 公開kitには汎用コード・説明・初期プロンプト・設定例・ライセンスを維持。examples/batch.example.jsonは1件の制作例。
- catalogはサイト・Release ZIP・非公開記録を別フォルダへ出力し、既存出力先を拒否。ソースZIPはreleasesへ新規作成し、保守データを含めない。
- 欠落していた第三者LICENSE文書2件を保存済みZIPから原文復元。LICENSEの著作権者consomme hollywoodを保持し、LICENSE_STATUSの説明を訂正。冒頭のcontributors表記は過去の記録。
- GitHub ReleasesとCloudflareへの外部公開は未実施。実公開URLは未設定。
- 整理後の検証: distは670素材・2248ファイル・2113ハッシュ・4455ローカルリンクでエラー0。移動した15 ZIPは台帳のサイズ・SHA-256と一致しCRC正常。分離した新規出力先で3素材から5 ZIPを構築し、リンク・ハッシュ検証正常。既存出力先と重複する出力先を拒否することも確認。1件バッチ例のdry-runと移行ハッシュ検証が成功。
2026-10-03追記: 公開kitにdocs/html_updates.mdを追加。HTMLの変更元、汎用の再構築・検証・Cloudflare配置、GitHub ReleasesのZIP公開から実URL反映までの順序を記載。外部公開は未実施。

## 2026-10-03 公開コピーの情報除去とAI向け説明JSON

- scripts/publication_privacy.pyとkit.py privacy clean/checkを公開kitへ追加。PNGの制作履歴・JPEGのEXIF等・Blendの保存画面や取り込み元やTextのローカルパスを新規コピーから除去する。原本・保守キャッシュ・移行ハッシュ・LICENSEは保持。圧縮Blendにはzstandardを使用。
- catalogは公開用コピーの除去と検査を自動実行する。素材ZIPへcatalog.json、asset.json、rig.json、存在する体形JSONを追加。対象形式だけを参照し、ZIP内の参照先とハッシュを検証する。独立JSONの改変説明は新名称に統一し、第三者ライセンス本文は保持。
- maintenanceとdistの丸ごとの結合は行わず、必要な公開素材・説明・ガイド・ライセンスだけを選ぶ。docs/privacy.mdに汎用コマンド、GitHub Releasesの構成、検査の限界を記載。
- 全670 Blendの展開後データはパス領域以外が同一。670 PNGの画素、773 BVHのハッシュ、114一覧画像が従来配布物と同一。5種類のBlendをBlenderで再読み込みし形状・行列・ボーン・制約・説明JSON・ライセンス文書の一致を確認。除去処理の7テストが成功。
- 旧配布物を非公開のmaintenance/history/pre-privacy-20261003へ保持し、検証済みのsiteをdist、15素材ZIPとkitソースZIPをreleasesへ採用した。サイト2248ファイル・2113ハッシュ・4455リンクはエラー0。素材ZIPには合計2705 JSONを収録し、参照・サイズ・ハッシュ・URLの15キーが整合。サイトとZIPの8254ファイル/収録項目を検査し、対象情報の検出0。最終記録はmaintenance/publication/current。
- 公開URLは未設定。外部公開は未実施。検査はパス・画像メタデータ・既知の認証情報パターンを対象とし、任意の氏名や画像内の人物を自動判別するものではない。

2026-10-03追記: ブラウザの1,000ファイル制限に対処するため、Wrangler CLI 4.147.0をGit対象外のmaintenance/tools/cloudflareへ導入。Node.js 24.9.0で起動とpages deployのヘルプを確認。現在のdistは2,248ファイルでWranglerの20,000ファイル上限内。docs/hosting.mdへ導入・ブラウザ認証・Pagesアップロード手順を追加。認証と外部公開は未実施。
2026-10-03追記: README.mdとREADME.htmlの冒頭に、チェックアウトしたフォルダをCodexで開いて導入・使い方を相談する案内を追加。ほかのAIコーディングエージェントでもAGENTS.mdを起点に利用できることを記載。
