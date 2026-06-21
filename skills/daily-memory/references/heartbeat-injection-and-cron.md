# Prompt injection + heartbeat wiring pattern

## Current preferred shape
- `prompt_builder.py` injects **today + yesterday memory full files** when present
- Missing memory files are ignored silently
- GOG injection keeps only the `未完了タスク` section
- `HEARTBEAT.md` or `heartbeat.md` is loaded from the same Hermes home directory as `SOUL.md`

## Why this shape
- Full memory files preserve tone and continuity better than section-only extraction for this user
- Ignoring missing files keeps the prompt cleaner than inserting `not found` placeholders
- GOG unfinished tasks are durable enough to matter in chat; day schedules should stay on-demand to avoid prompt bloat
- HEARTBEAT rules belong beside identity rules so proactive messaging can reuse the same personality anchor

## Heartbeat wiring note
- 現在の heartbeat は `$HERMES_HOME/hooks/heartbeat-hook/handler.py` の same-session hook だけを使う
- 旧 `scripts/heartbeat/heartbeat.py` と heartbeat cron は削除済みで、fresh session 側の保険運用はしていない

## Verification targets
- `prompt_builder.py` imports cleanly
- helper probes show memory, GOG, and heartbeat sections all present when expected
- the heartbeat script exits 0 and stays silent when the model decides not to send anything
