# AGENTS

この repo は `memory-plugin` の live plugin surface だよ。

## Scope Guard

触ってよいのは原則として次だけ。

- `README.md`
- `AGENTS.md`
- `.gitignore`
- `__init__.py`
- `plugin.yaml`
- `skills/`

## 方針

- 実運用の plugin surface は `/opt/data/plugins/memory/`
- tracked plugin code の正本は `origin/main` を基準に扱う
- `main` push の自動反映は停止中で、tracked code の更新は必要時に host 上で手動 `git pull --ff-only` へ寄せる
- runtime state は `/opt/data/plugins/memory/state/` に残し、source repo へは持ち込まない
- plugin 変更が必要なら、関連する `dev` lane で確認してから live plugin surface へ反映する
