# memory rename checklist

このメモは legacy な命名整理の確認用だよ。現在の workspace では、日次記録ファイルの実体は `workspace/diaries/` を優先し、`memory` plugin/tool/skill 名は残す。`workspace/memory/` から `workspace/diaries/` へ移す時の詳細は `references/workspace-diaries-rename-checklist.md` を見る。

## 追従対象
- 実ディレクトリ名と script path
- cron job 名
- state JSON の `source`
- designs / notes / skills の説明文
- 監視 script の legacy path 互換処理

## 最低限の検証
- 旧 path（例: `scripts/diary` や旧 feature 名）の残存参照が検索で 0 件
- 旧 cron job 名が cron 一覧から消えている
- script の軽量サブコマンドが成功する
- 関連 Python script が `py_compile` を通る

## 現行例
- script feature は `/opt/data/scripts/diaries/`
- 日次記録ファイルは `/opt/data/workspace/diaries/YYYY-MM-DD.md`
- `memory` plugin / memory tool / skill 名は残す
- state JSON の `source` は必要に応じて `diaries/...` へ更新
