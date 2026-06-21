# memory helper scripts

## 使う時

- daily memory の中身をざっと見たい時
- 過去の daily memory を語句で追いたい時
- memory の保存範囲や欠け日を確認したい時
- こういう軽量 helper の入口をまとめて見たい時は、まず `memory-search` を開く

## canonical scripts

すべての正本は `/opt/data/scripts/memory/` に置く。

### 今日と昨日を読む

```bash
python3 /opt/data/scripts/memory/read-recent-memory.py
python3 /opt/data/scripts/memory/read-recent-memory.py --format json --include-missing
```

- 既定は **今日 → 昨日** の順
- `--include-missing` を付けると、存在しない日も `exists: no` で出す

### memory 内を検索する

```bash
python3 /opt/data/scripts/memory/search-memory.py 相棒
python3 /opt/data/scripts/memory/search-memory.py 'heartbeat|memory' --limit 20
python3 /opt/data/scripts/memory/search-memory.py '石垣' --format json
```

- query は regex として扱う
- 既定は case-insensitive
- 人間が読む時は markdown、後段処理へ渡す時は `--format json`

### memory の保存範囲を取る

```bash
python3 /opt/data/scripts/memory/list-memory-range.py
python3 /opt/data/scripts/memory/list-memory-range.py --show-missing
python3 /opt/data/scripts/memory/list-memory-range.py --format json
```

- `first_date` / `last_date` / `count` / `missing_dates` を見る
- LIN の始まりや、抜け日の点検に向く

## 運用メモ

- helper script を増やす時も、skill 配下へ複製しない
- skill 側は入口と説明だけ持ち、実装正本は `/opt/data/scripts/memory/` に寄せる
- `daily-memory` skill の bare 正本は `/opt/data/plugins/memory/skills/daily-memory/` に置き、discovery は `skills.external_dirs` 経由へ一本化する
- 検索・一覧・今日昨日参照も、別 skill へ分けず `daily-memory` にまとめて持つ
- runtime context build / session sync 系の companion skill は `/opt/data/skills/LIN/event-context/` に置く
