# gateway memory import path fallback

## いつ使うか
- `daily-memory` skill は見えているのに、gateway の live memory 注入だけ動かない時
- ログに `Failed to resolve memory context` や `No module named 'plugins.memory.dashboard'` が出る時
- bare surfaced skill 化や plugin 配置整理のあと、dashboard `plugin_api.py` は存在するのに runtime import だけ落ちる時

## 症状の見分け方
- `skill_view("daily-memory")` は通る
- dashboard 側の `plugin_api.py` は存在する
- でも gateway ログで `from plugins.memory.dashboard.plugin_api import ...` 由来の import error が出る

## まず切り分けること
1. **skill の露出**と**Python import 経路**を分けて考える
   - `register_skill(...)` は主に skill の discoverability / namespaced 露出の話
   - 今回のような `plugins.memory.dashboard` エラーは、まず Python package 解決の問題として疑う
2. runtime code が `/opt/hermes/...` で動いていても、正本が `/opt/data/workspace/infra/overrides/...` かを先に確認する
3. compose で `./overrides/run.py:/opt/hermes/gateway/run.py:ro` のような bind mount があるなら、**編集は override 正本側**へ入れる

## 実務の修理方針
- `run.py` 側で `from plugins.memory.dashboard.plugin_api import ...` を直接前提にしすぎない
- まず通常 import を試し、`ModuleNotFoundError` の時だけ fallback する
- fallback では `importlib.util.spec_from_file_location(...)` で次を候補にする
  1. `get_hermes_home() / "plugins" / "memory" / "dashboard" / "plugin_api.py"`
  2. bundled plugins 側の `memory/dashboard/plugin_api.py`
- 読み込めた module から `load_config` / `resolve_memory_injection_policy` / `update_memory_resolution_state` を取り出して続行する

## なぜこれで直すか
- bare skill discovery を守りつつ、live runtime の import 経路だけを補強できる
- `register_skill` を戻さなくても、gateway の memory 注入を復旧できる
- skill の UX と Python import を混同しないで済む

## 検証
- `py_compile` で override `run.py` の構文確認
- fallback loader 単体で `plugin_api.py` を file-path import し、必要関数が見えるか確認
- compose 再適用 / コンテナ再作成 / gateway 再起動後に、ログから
  - `Failed to resolve memory context`
  - `No module named 'plugins.memory.dashboard'`
  が消えるか見る

## pitfalls
- `register_skill` を戻せば直る、と短絡しない
- `/opt/hermes/gateway/run.py` を直接直して終わりにしない。override mount があるなら正本はそっち
- source 側を直しただけで live 反映済みと見なさない。bind mount / compose 再適用 / 再起動の確認まで必要
