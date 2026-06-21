# memory rename checklist

この skill で daily memory 系の命名を `diary` から `memory` に寄せる時の確認メモ。

## 追従対象
- 実ディレクトリ名と script path
- cron job 名
- state JSON の `source`
- designs / notes / skills の説明文
- 監視 script の legacy path 互換処理

## 最低限の検証
- 旧 path (`scripts/diary` など) の残存参照が検索で 0 件
- 旧 cron job 名が cron 一覧から消えている
- script の軽量サブコマンド（例: `status`）が成功する
- 関連 Python script が `py_compile` を通る

## 実例
- `scripts/diary/` → `scripts/memory/`
- `create-diary-and-note` → `create-memory-and-note`
- `sync-diary` → `sync-memory`
- state JSON の `source` も `memory/...` へ更新
