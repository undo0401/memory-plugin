(function () {
  "use strict";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;
  const { React } = SDK;
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button, Input, Label } = SDK.components;
  const { useState, useEffect, useCallback } = SDK.hooks;
  const h = React.createElement;
  const Textarea = SDK.components.Textarea || function (props) { return h("textarea", props); };
  const Checkbox = SDK.components.Checkbox || function (props) {
    const { checked, onCheckedChange, ...rest } = props;
    return h("input", Object.assign({ type: "checkbox", checked: !!checked, onChange: function (e) { if (onCheckedChange) onCheckedChange(e.target.checked); } }, rest));
  };
  function SelectField(props) {
    const options = Array.isArray(props.options) ? props.options : [];
    return h("select", {
      className: props.className || "lin-panel__input",
      value: props.value,
      onChange: function (e) { if (props.onChange) props.onChange(e.target.value); }
    }, options.map(function (opt) {
      return h("option", { key: opt.value, value: opt.value }, opt.label);
    }));
  }

  function api(path, options) { return SDK.fetchJSON("/api/plugins/memory" + path, options); }
  function parseApiErrorMessage(err) {
    const raw = (err && err.message) ? String(err.message) : String(err || "");
    const m = raw.match(/^(\d{3}):\s*(.*)$/s);
    const body = m ? m[2] : raw;
    try { const parsed = JSON.parse(body); if (parsed && typeof parsed.detail === "string") return parsed.detail; } catch (_e) {}
    return body || raw;
  }
  function statusOn(value) {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") return ["1", "true", "yes", "on", "enabled"].includes(value.trim().toLowerCase());
    return false;
  }
  function splitLines(text) {
    return String(text || "").split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
  }
  function truncate(value, max) {
    const text = String(value || "");
    const limit = max || 120;
    return text.length > limit ? text.slice(0, limit) + "…" : text;
  }
  function StatusBadge(props) {
    const on = statusOn(props.value);
    return h(Badge, { className: on ? "lin-panel__badge lin-panel__badge--on" : "lin-panel__badge lin-panel__badge--off" }, on ? "enabled" : "disabled");
  }
  function Pill(props) {
    return h("span", { className: "lin-panel__pill lin-panel__pill--" + (props.tone || "muted") }, props.children);
  }
  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }
  function formatTimestamp(value) {
    var text = String(value || "").trim();
    if (!text) return "(never)";
    return text;
  }
  function defaultLane(index) {
    const n = (index || 0) + 1;
    return {
      name: "memory-" + n,
      enabled: true,
      prompt: "",
      include_current_time: false,
      include_current_source: false,
      include_session_gap: false,
      idle_seconds: 0,
      reinject_interval_minutes: 0,
      target_sessions: [],
      target_channels: [],
      target_profiles: ["default"],
      exclude_sessions: [],
      exclude_channels: [],
      exclude_profiles: [],
      snapshot_files: []
    };
  }
  function defaultTargetKind(lane) {
    const sessions = Array.isArray(lane && lane.target_sessions) ? lane.target_sessions : [];
    const channels = Array.isArray(lane && lane.target_channels) ? lane.target_channels : [];
    const excludeSessions = Array.isArray(lane && lane.exclude_sessions) ? lane.exclude_sessions : [];
    const excludeChannels = Array.isArray(lane && lane.exclude_channels) ? lane.exclude_channels : [];
    if (channels.length || excludeChannels.length) return "channel";
    if (sessions.length || excludeSessions.length) return "session";
    return "session";
  }

  function Page() {
    const [state, setState] = useState({
      loading: true,
      saving: false,
      error: "",
      banner: "",
      payload: null,
      form: null,
      selectedLaneName: null,
      view: "list"
    });
    const laneEpochRef = React.useRef(0);
    const activeLaneRef = React.useRef(null);

    useEffect(function () {
      activeLaneRef.current = state.selectedLaneName || null;
    }, [state.selectedLaneName]);

    const syncForm = useCallback(function (payload, desiredLaneName) {
      const config = (payload && payload.config) || { lanes: [] };
      const lanes = Array.isArray(config.lanes) ? config.lanes : [];
      const selectedName = desiredLaneName || (lanes[0] && lanes[0].name) || null;
      const lane = lanes.find(function (item) { return String(item.name) === String(selectedName); }) || lanes[0] || defaultLane(0);
      setState(function (prev) {
        return Object.assign({}, prev, {
          payload: payload,
          selectedLaneName: lane.name || selectedName,
          form: {
            name: String(lane.name || ""),
            enabled: !!lane.enabled,
            promptText: String(lane.prompt || ""),
            includeCurrentTime: !!lane.include_current_time,
            includeCurrentSource: !!lane.include_current_source,
            includeSessionGap: !!lane.include_session_gap,
            targetKind: defaultTargetKind(lane),
            targetSessionsText: ((lane.target_sessions || [])).join("\n"),
            targetChannelsText: ((lane.target_channels || [])).join("\n"),
            targetProfile: ((lane.target_profiles || [])[0]) || "default",
            excludeSessionsText: ((lane.exclude_sessions || [])).join("\n"),
            excludeChannelsText: ((lane.exclude_channels || [])).join("\n"),
            excludeProfilesText: ((lane.exclude_profiles || [])).join("\n"),
            snapshotFilesText: ((lane.snapshot_files || [])).join("\n")
          }
        });
      });
    }, []);

    const load = useCallback(function (desiredLaneName) {
      const laneEpoch = laneEpochRef.current;
      const fallbackLaneName = desiredLaneName || activeLaneRef.current;
      setState(function (prev) { return Object.assign({}, prev, { loading: true, error: "" }); });
      api("/config").then(function (payload) {
        setState(function (prev) { return Object.assign({}, prev, { loading: false, payload: payload }); });
        if (laneEpoch !== laneEpochRef.current) return;
        syncForm(payload, fallbackLaneName || activeLaneRef.current);
      }).catch(function (err) {
        setState(function (prev) { return Object.assign({}, prev, { loading: false, error: parseApiErrorMessage(err) }); });
      });
    }, [syncForm]);

    useEffect(function () { load(); }, [load]);

    function setFormValue(key, value) {
      setState(function (prev) { return Object.assign({}, prev, { form: Object.assign({}, prev.form || {}, { [key]: value }) }); });
    }
    function currentTargetTextKey() {
      return String((state.form && state.form.targetKind) || "session") === "channel" ? "targetChannelsText" : "targetSessionsText";
    }
    function currentExcludeTextKey() {
      return String((state.form && state.form.targetKind) || "session") === "channel" ? "excludeChannelsText" : "excludeSessionsText";
    }
    function currentTargetLabel() {
      return "target";
    }
    function currentExcludeLabel() {
      return "exclude";
    }
    function currentTargetPlaceholder() {
      return String((state.form && state.form.targetKind) || "session") === "channel" ? "empty = all channels" : "empty = all sessions";
    }
    function currentExcludePlaceholder() {
      return String((state.form && state.form.targetKind) || "session") === "channel" ? "empty = none" : "empty = none";
    }
    function currentConfig() {
      return (state.payload && state.payload.config) || { schema_version: 1, description: "memory dashboard v3 config", lanes: [] };
    }
    function currentLanes() {
      return Array.isArray(currentConfig().lanes) ? currentConfig().lanes : [];
    }
    function currentLane() {
      const lanes = currentLanes();
      return lanes.find(function (lane) { return String(lane.name) === String(state.selectedLaneName); }) || lanes[0] || null;
    }
    function laneRuntime(name) {
      var runtime = (state.payload && state.payload.lane_runtime) || {};
      return runtime[String(name || "")] || null;
    }
    function lanePreview(name) {
      var previews = (state.payload && state.payload.lane_previews) || {};
      return previews[String(name || "")] || null;
    }
    function profileOptions() {
      var rows = (state.payload && Array.isArray(state.payload.available_profiles)) ? state.payload.available_profiles : [];
      var seen = {};
      var options = rows.map(function (item) {
        var value = String((item && item.value) || "").trim();
        if (!value || seen[value]) return null;
        seen[value] = true;
        return { value: value, label: String((item && item.label) || value) };
      }).filter(Boolean);
      if (!seen.default) options.unshift({ value: "default", label: "default" });
      var current = String((state.form && state.form.targetProfile) || "default").trim() || "default";
      if (!seen[current]) options.push({ value: current, label: current });
      return options;
    }
    function buildLanePayload() {
      const form = state.form || {};
      const targetKind = String(form.targetKind || "session") === "channel" ? "channel" : "session";
      return {
        name: String(form.name || "").trim(),
        enabled: !!form.enabled,
        prompt: String(form.promptText || "").trim(),
        include_current_time: !!form.includeCurrentTime,
        include_current_source: !!form.includeCurrentSource,
        include_session_gap: !!form.includeSessionGap,
        idle_seconds: 0,
        reinject_interval_minutes: 0,
        target_sessions: targetKind === "session" ? splitLines(form.targetSessionsText) : [],
        target_channels: targetKind === "channel" ? splitLines(form.targetChannelsText) : [],
        target_profiles: [String(form.targetProfile || "default").trim() || "default"],
        exclude_sessions: targetKind === "session" ? splitLines(form.excludeSessionsText) : [],
        exclude_channels: targetKind === "channel" ? splitLines(form.excludeChannelsText) : [],
        exclude_profiles: splitLines(form.excludeProfilesText),
        snapshot_files: splitLines(form.snapshotFilesText)
      };
    }
    function buildConfigPayloadFromSelectedLane() {
      const config = clone(currentConfig());
      config.schema_version = 1;
      config.description = String(config.description || "memory dashboard v3 config");
      const lanes = currentLanes().slice();
      const nextLane = buildLanePayload();
      if (!nextLane.name) throw new Error("name is required");
      const duplicate = lanes.find(function (lane) { return String(lane.name) === nextLane.name; });
      if (duplicate && String(duplicate.name) !== String(state.selectedLaneName)) throw new Error("name must be unique");
      const index = lanes.findIndex(function (lane) { return String(lane.name) === String(state.selectedLaneName); });
      if (index >= 0) lanes[index] = nextLane;
      else lanes.push(nextLane);
      config.lanes = lanes;
      return config;
    }
    function persistConfig(payload, successMessage, nextState, syncLaneName) {
      const laneEpoch = laneEpochRef.current;
      const targetLaneName = syncLaneName || activeLaneRef.current;
      setState(function (prev) { return Object.assign({}, prev, { saving: true, error: "", banner: "" }, nextState || {}); });
      api("/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then(function (nextPayload) {
        var wakeInfo = nextPayload && nextPayload.watcher ? (" · watcher wake " + String(nextPayload.watcher.woken_watchers || 0)) : "";
        var laneMoved = laneEpoch !== laneEpochRef.current;
        setState(function (prev) {
          var baseState = { saving: false, banner: successMessage + wakeInfo, payload: nextPayload };
          if (laneMoved) return Object.assign({}, prev, baseState);
          return Object.assign({}, prev, Object.assign({}, baseState, nextState || {}));
        });
        if (laneMoved) return;
        syncForm(nextPayload, targetLaneName || activeLaneRef.current);
      }).catch(function (err) {
        setState(function (prev) { return Object.assign({}, prev, { saving: false, error: parseApiErrorMessage(err) }); });
      });
    }
    function save() {
      var payload;
      var selected;
      var nextLaneName;
      try {
        payload = buildConfigPayloadFromSelectedLane();
        selected = payload.lanes.find(function (lane) { return String(lane.name) === String(state.selectedLaneName); });
        nextLaneName = selected ? selected.name : ((payload.lanes[0] && payload.lanes[0].name) || state.selectedLaneName);
      } catch (err) {
        setState(function (prev) { return Object.assign({}, prev, { error: "save parse error: " + err.message, banner: "" }); });
        return;
      }
      persistConfig(payload, "Saved", { view: "list", selectedLaneName: nextLaneName || null }, nextLaneName);
    }
    function openLane(laneName) {
      laneEpochRef.current += 1;
      activeLaneRef.current = laneName;
      setState(function (prev) { return Object.assign({}, prev, { selectedLaneName: laneName, view: "detail", saving: false }); });
      syncForm(state.payload || { config: currentConfig() }, laneName);
    }
    function backToList() {
      setState(function (prev) { return Object.assign({}, prev, { view: "list" }); });
    }
    function createLane() {
      var lanes = currentLanes();
      var lane = defaultLane(lanes.length);
      var usedNames = new Set(lanes.map(function (item) { return String(item.name); }));
      while (usedNames.has(lane.name)) {
        lane = defaultLane(usedNames.size + 1);
      }
      var payload = clone(currentConfig());
      payload.lanes = lanes.concat([lane]);
      persistConfig(payload, "Memory added", { view: "detail", selectedLaneName: lane.name }, lane.name);
    }
    function toggleLaneEnabled(laneName, enabled) {
      var payload = clone(currentConfig());
      var lanes = Array.isArray(payload.lanes) ? payload.lanes.slice() : [];
      var index = lanes.findIndex(function (lane) { return String(lane.name) === String(laneName); });
      if (index < 0) return;
      lanes[index] = Object.assign({}, lanes[index], { enabled: !!enabled });
      payload.lanes = lanes;
      persistConfig(payload, enabled ? "Memory enabled" : "Memory disabled");
    }
    function toggleSelectedLaneEnabled(enabled) {
      var selectedLaneName = state.selectedLaneName;
      if (!selectedLaneName) return;
      var payload = clone(currentConfig());
      var lanes = Array.isArray(payload.lanes) ? payload.lanes.slice() : [];
      var index = lanes.findIndex(function (item) { return String(item.name) === String(selectedLaneName); });
      if (index < 0) return;
      lanes[index] = Object.assign({}, lanes[index], { enabled: !!enabled });
      payload.lanes = lanes;
      persistConfig(payload, enabled ? "Memory enabled" : "Memory disabled", {
        form: Object.assign({}, state.form || {}, { enabled: !!enabled })
      }, selectedLaneName);
    }

    var payload = state.payload || {};
    var form = state.form || {};
    var lanes = currentLanes();
    var lane = currentLane();

    function renderList() {
      return h("div", { className: "lin-panel" },
        h(Card, { className: "lin-panel__hero" },
          h(CardHeader, null,
            h("div", { className: "lin-panel__titleRow" },
              h(CardTitle, null, "memory"),
              h("div", { className: "lin-panel__titleMeta" },
                h(Pill, { tone: "good" }, String(lanes.length) + " memory setting" + (lanes.length === 1 ? "" : "s")),
                h(Button, { type: "button", onClick: createLane }, state.saving ? "Saving..." : "New setting")
              )
            )
          ),
          h(CardContent, { className: "lin-panel__heroContent" },
            h("p", { className: "lin-panel__lead" }, "一覧から memory 設定を選んで、詳細へ入る形だよ。heartbeat と同じく、まず全体を見てから個別設定へ降りる。"),
            payload.config_file ? h("p", { className: "lin-panel__path" }, "config: " + payload.config_file) : null,
            state.error ? h("p", { className: "lin-panel__error" }, state.error) : null,
            state.banner ? h("p", { className: "lin-panel__banner" }, state.banner) : null
          )
        ),
        h("div", { className: "lin-panel__list" },
          lanes.map(function (item) {
            var files = Array.isArray(item.snapshot_files) ? item.snapshot_files : [];
            var targetKind = ((Array.isArray(item.target_channels) && item.target_channels.length) || (Array.isArray(item.exclude_channels) && item.exclude_channels.length)) ? "channel" : "session";
            var targetValues = targetKind === "channel" ? (item.target_channels || []) : (item.target_sessions || []);
            var excludeValues = targetKind === "channel" ? (item.exclude_channels || []) : (item.exclude_sessions || []);
            var targetLabel = targetKind + " · " + (targetValues.join(", ") || "(all)");
            var excludeLabel = targetKind + " · " + (excludeValues.join(", ") || "(none)");
            var profileLabel = (item.target_profiles || []).join(", ") || "default";
            var promptPreview = truncate(String(item.prompt || ""), 120) || "(none)";
            var runtimeInfo = laneRuntime(item.name) || {};
            var previewInfo = lanePreview(item.name) || {};
            return h(Card, { key: item.name, className: "lin-panel__laneCard" },
              h(CardContent, { className: "lin-panel__laneBody" },
                h("div", { className: "lin-panel__laneMain" },
                  h("div", { className: "lin-panel__laneTitleRow" },
                    h("div", null,
                      h("div", { className: "lin-panel__laneTitle" }, String(item.name || "memory"))
                    ),
                    h("div", { className: "lin-panel__titleMeta" },
                      h(Pill, { tone: files.length ? "good" : "muted" }, String(files.length) + " files"),
                      h("label", { className: "lin-panel__fieldRowCheckbox" },
                        h(Checkbox, { checked: !!item.enabled, disabled: !!state.saving, onCheckedChange: function (v) { toggleLaneEnabled(item.name, !!v); } }),
                        h("span", null, item.enabled ? "enabled" : "disabled")
                      )
                    )
                  ),
                  h("div", { className: "lin-panel__laneMeta" },
                    h("span", null, "last applied · " + formatTimestamp(runtimeInfo.last_applied_at)),
                    h("span", null, "target · " + targetLabel),
                    h("span", null, "exclude · " + excludeLabel),
                    h("span", null, "profiles · " + profileLabel),
                    h("span", null, "prompt · " + promptPreview),
                    h("span", null, "current time · " + (item.include_current_time ? "inject" : "skip")),
                    h("span", null, "current channel · " + (item.include_current_source ? "inject" : "skip")),
                    h("span", null, "session gap · " + (item.include_session_gap ? "inject" : "skip")),
                    h("span", null, "preview · " + (truncate(String(previewInfo.excerpt || ""), 160) || "(none)")),
                    h("span", null, "files · " + (files.length ? truncate(files.join(", "), 160) : "(none)"))
                  )
                ),
                h("div", { className: "lin-panel__laneActions" },
                  h(Button, { type: "button", onClick: function () { openLane(item.name); } }, "Open")
                )
              )
            );
          })
        )
      );
    }

    function renderDetail() {
      var summaryTargetKind = String(form.targetKind || "session") === "channel" ? "channel" : "session";
      var summaryTargetText = summaryTargetKind === "channel"
        ? (splitLines(form.targetChannelsText).join(", ") || "(all)")
        : (splitLines(form.targetSessionsText).join(", ") || "(all)");
      var summaryExcludeText = summaryTargetKind === "channel"
        ? (splitLines(form.excludeChannelsText).join(", ") || "(none)")
        : (splitLines(form.excludeSessionsText).join(", ") || "(none)");
      var summaryTargetProfiles = String(form.targetProfile || "default").trim() || "default";
      var summaryExcludeProfiles = splitLines(form.excludeProfilesText).join(", ") || "(none)";
      var summaryCurrentTime = form.includeCurrentTime ? "inject" : "skip";
      var summaryCurrentSource = form.includeCurrentSource ? "inject" : "skip";
      var summarySessionGap = form.includeSessionGap ? "inject" : "skip";
      var summaryPromptText = String(form.promptText || "").trim() || "(none)";
      var runtimeInfo = laneRuntime(form.name) || {};
      var previewInfo = lanePreview(form.name) || {};
      return h("div", { className: "lin-panel" },
        h(Card, { className: "lin-panel__hero" },
          h(CardHeader, null,
            h("div", { className: "lin-panel__titleRow" },
              h("div", { className: "lin-panel__titleStack" },
                h(Button, { type: "button", onClick: backToList }, "← Back to list"),
                h(CardTitle, null, form.name || "memory")
              ),
              h("div", { className: "lin-panel__titleMeta" },
                h(Pill, { tone: splitLines(form.snapshotFilesText).length ? "good" : "muted" }, String(splitLines(form.snapshotFilesText).length) + " files"),
                h(StatusBadge, { value: form.enabled })
              )
            )
          ),
          h(CardContent, { className: "lin-panel__heroContent" },
            h("p", { className: "lin-panel__lead" }, "一覧から選んだ memory 設定をここで触るよ。heartbeat の sibling 設定面として、全体→個別の流れをそのまま寄せてある。"),
            h("p", { className: "lin-panel__path" }, "name: " + (form.name || "")),
            state.error ? h("p", { className: "lin-panel__error" }, state.error) : null,
            state.banner ? h("p", { className: "lin-panel__banner" }, state.banner) : null
          )
        ),
        h("div", { className: "lin-panel__grid" },
          h(Card, { className: "lin-panel__card" },
            h(CardHeader, null, h(CardTitle, null, "Settings")),
            h(CardContent, { className: "lin-panel__content" },
              h("div", { className: "lin-panel__fieldRowCheckbox" }, h(Checkbox, { checked: !!form.enabled, disabled: !!state.saving, onCheckedChange: function (v) { toggleSelectedLaneEnabled(!!v); } }), h(Label, null, form.enabled ? "enabled" : "disabled")),
              h("div", { className: "lin-panel__field" }, h(Label, null, "name"), h(Input, { className: "lin-panel__input", value: form.name || "", onChange: function (e) { setFormValue("name", e.target.value); } })),
              h("div", { className: "lin-panel__field" }, h(Label, null, "prompt"), h(Textarea, { className: "lin-panel__textarea", value: form.promptText || "", onChange: function (e) { setFormValue("promptText", e.target.value); }, placeholder: "このチャットでは短めに返す\n必要なら数行で返す\nこの lane 用の補助システムプロンプトを書く" }), h("p", { className: "lin-panel__hint" }, "snapshot file とは別に、この lane 専用の補助 prompt をそのまま memory injection へ積めるよ。チャットごとの返答の長さ、温度感、優先ルールみたいな system prompt 的な指示をここへ置く想定。")),
              h("div", { className: "lin-panel__fieldRowCheckbox" }, h(Checkbox, { checked: !!form.includeCurrentTime, disabled: !!state.saving, onCheckedChange: function (v) { setFormValue("includeCurrentTime", !!v); } }), h(Label, null, "inject current time")),
              h("div", { className: "lin-panel__fieldRowCheckbox" }, h(Checkbox, { checked: !!form.includeCurrentSource, disabled: !!state.saving, onCheckedChange: function (v) { setFormValue("includeCurrentSource", !!v); } }), h(Label, null, "inject current channel")),
              h("div", { className: "lin-panel__fieldRowCheckbox" }, h(Checkbox, { checked: !!form.includeSessionGap, disabled: !!state.saving, onCheckedChange: function (v) { setFormValue("includeSessionGap", !!v); } }), h(Label, null, "inject session gap")),
              h("div", { className: "lin-panel__field" }, h(Label, null, "target type"), h(SelectField, { value: form.targetKind || "session", onChange: function (v) { setFormValue("targetKind", v); }, options: [
                { value: "session", label: "Session" },
                { value: "channel", label: "Channel" }
              ] })),
              h("div", { className: "lin-panel__field" }, h(Label, null, currentTargetLabel()), h(Textarea, { className: "lin-panel__textarea", value: form[currentTargetTextKey()] || "", onChange: function (e) { setFormValue(currentTargetTextKey(), e.target.value); }, placeholder: currentTargetPlaceholder() })),
              h("div", { className: "lin-panel__field" }, h(Label, null, currentExcludeLabel()), h(Textarea, { className: "lin-panel__textarea", value: form[currentExcludeTextKey()] || "", onChange: function (e) { setFormValue(currentExcludeTextKey(), e.target.value); }, placeholder: currentExcludePlaceholder() })),
              h("div", { className: "lin-panel__field" }, h(Label, null, "target profile"), h(SelectField, { value: form.targetProfile || "default", options: profileOptions(), onChange: function (value) { setFormValue("targetProfile", value || "default"); } })),
              h("div", { className: "lin-panel__field" }, h(Label, null, "exclude profiles"), h(Textarea, { className: "lin-panel__textarea", value: form.excludeProfilesText || "", onChange: function (e) { setFormValue("excludeProfilesText", e.target.value); }, placeholder: "empty = none" })),
              h("div", { className: "lin-panel__field" }, h(Label, null, "snapshot files"), h(Textarea, { className: "lin-panel__textarea", value: form.snapshotFilesText || "", onChange: function (e) { setFormValue("snapshotFilesText", e.target.value); }, placeholder: "/opt/data/state/MEMORY_EVENT_CONTEXT.md" })),
              h("div", { className: "lin-panel__buttonRow" },
                h(Button, { type: "button", onClick: save }, state.saving ? "Saving..." : "Save")
              )
            )
          ),
          h(Card, { className: "lin-panel__card" },
            h(CardHeader, null, h(CardTitle, null, "Summary / preview")),
            h(CardContent, { className: "lin-panel__content" },
              h("div", { className: "lin-panel__summary" },
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "last applied"), h("dd", null, formatTimestamp(runtimeInfo.last_applied_at))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "last reason"), h("dd", null, String(runtimeInfo.last_decision_reason || "(none)"))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "matched sessions"), h("dd", null, String(runtimeInfo.matched_session_count || 0))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "prompt"), h("dd", null, summaryPromptText)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "current time"), h("dd", null, summaryCurrentTime)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "current channel"), h("dd", null, summaryCurrentSource)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "session gap"), h("dd", null, summarySessionGap)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "target"), h("dd", null, summaryTargetKind + " · " + summaryTargetText)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "exclude"), h("dd", null, summaryTargetKind + " · " + summaryExcludeText)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "target profile"), h("dd", null, summaryTargetProfiles)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "exclude profiles"), h("dd", null, summaryExcludeProfiles)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "files"), h("dd", null, splitLines(form.snapshotFilesText).join(", ") || "(none)"))
              ),
              h("div", { className: "lin-panel__summary" },
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "preview"), h("dd", null, previewInfo.has_preview ? "ready" : "(none)")),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "source session"), h("dd", null, String(runtimeInfo.last_session_key || "(none)")))
              ),
              h("pre", { className: "lin-panel__textarea", style: { whiteSpace: "pre-wrap" } }, String(previewInfo.text || "(preview empty)"))
            )
          )
        )
      );
    }

    return state.view === "detail" && lane ? renderDetail() : renderList();
  }

  window.__HERMES_PLUGINS__.register("memory", Page);
})();
