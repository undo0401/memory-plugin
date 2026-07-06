# Retired lin-ops project note

`/opt/data/projects/lin-ops/` は、memory / heartbeat の sidecar control plane を別 project として持つ試作の残骸だったよ。

## project 側にあったもの

- `src/lin_ops/memory/session_intro.py`
  - `/opt/data/workspace/memory/YYYY-MM-DD.md` の **昨日 / 今日** を読み、session-open 向け text を組み立てる試作
- `src/lin_ops/api.py`
  - watcher / injection 数を返すだけの未接続 API facade
- `docs/deployment.md`, `designs/project-layout.md`
  - compose / supervisor / worker 常駐を将来追加する前提のメモ

## いまの採用形

現行では sidecar project を起こさず、責務をこう分ける。

- session-open injection の selector / file loading / text assembly
  - `memory` plugin backend (`/opt/data/plugins/memory/dashboard/plugin_api.py`)
- snapshot 生成
  - memory plugin の責務外。producer 側の diary / event-context pipeline が担う
- first-turn への prepend
  - `/opt/hermes/gateway/run.py`

## 退役判断

`lin-ops` 由来のコードは次の理由で現行正本へ残さない。

1. daily memory の生ファイル直読みより、`snapshot_files` を lane ごとに読む現行 contract のほうが source of truth が明確
2. `lin_ops.api` は dashboard plugin と未接続で、runtime 経路に入っていなかった
3. compose / worker / supervisor 前提は、現行の plugin-centered 構成と衝突する

## 残した知見

- 「session-open 向けに yesterday / today をまとめて見たい」という意図自体は有効
- ただし現行では plugin が daily memory 生ファイルを直読せず、producer が用意した markdown snapshot を lane ごとに読む
- sidecar 化の再検討が必要になっても、この note は **歴史メモ** として扱い、現行仕様の正本にはしない
