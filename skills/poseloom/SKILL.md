---
name: poseloom
description: ComfyUIとBlenderで人物画像から3Dポーズを制作し、BVH・Blend配布サイトを保守する。導入、標準テンプレート接続、素材追加に使う。
---

リポジトリのAGENTS.mdを読む。既定ルートはこのファイルの2階層上。スキルだけを別の場所へコピーした場合は利用者のリポジトリを特定する。

初期参考画像はimagegen/ComfyUI/手持ち画像から利用者に選んでもらう。指定済みなら再質問しない。imagegenを使える場合はエージェント側の画像生成機能で作り、保存した画像をpose/pairまたはbatch import-sourcesへ渡す。初期画像のためのQwen導入を強制しない。imagegenが使えない場合は説明して代替方法を選んでもらう。生成方法・プロンプト・出所を記録する。

導入・ダウンロードの選択はdocs/setup.md、標準テンプレートはdocs/workflows.md、制作・670素材保守はdocs/maintenance.md、公開はdocs/hosting.mdを読む。

既存ComfyUIとそのPythonを確認し、自動/手動取得の希望を反映する。実node ID/inputを確認してAPIグラフを接続する。原本は上書きせず新規出力先へ。SAM3D解析元FBXと配布Blend由来FBXを混同しない。失敗・中断の再試行や契約解除を勝手にしない。12GBは未検証なので1件から確認。ライセンスとNOTICEを保持し、独自コードはMIT（LICENSE）で、第三者由来の条件は別に保持する。公開URL未確定を明示。完了作業と実測範囲をdocs/progress.mdへ記録する。
