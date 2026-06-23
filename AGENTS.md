# AGENTS

この repo は `memory-plugin` の source repo だよ。

## Scope Guard

触ってよいのは原則として次だけ。

- `README.md`
- `AGENTS.md`
- `.gitignore`
- `.github/workflows/`
- `plugin.yaml`
- `__init__.py`
- `runtime.py`
- `runtime_tick.py`
- `dashboard/`
- `config/`
- `references/`
- `skills/`

## 方針

- 実運用の plugin surface は `/opt/data/plugins/memory/`
- source owner repo は `/opt/data/src/memory-plugin/`
- tracked plugin code の正本は `origin/main` だけ
- `main` push の自動反映は停止中で、tracked code の更新は必要時に host 上で手動 `git pull --ff-only` へ寄せる
- runtime state は `/opt/data/plugins/memory/state/` に残し、source repo へは持ち込まない
