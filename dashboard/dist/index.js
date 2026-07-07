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
  function promptPreview(prompt) {
    const text = String(prompt || "").trim();
    return text ? truncate(text, 160) : "(prompt not set yet)";
  }
  function StatusBadge(props) {
    const on = statusOn(props.value);
    return h(Badge, { className: on ? "lin-panel__badge lin-panel__badge--on" : "lin-panel__badge lin-panel__badge--off" }, on ? "enabled" : "disabled");
  }
  function Pill(props) {
    return h("span", { className: "lin-panel__pill lin-panel__pill--" + (props.tone || "muted") }, props.children);
  }
  function asCount(value, fallback) {
    var n = Number(value);
    return Number.isFinite(n) ? n : (Number.isFinite(Number(fallback)) ? Number(fallback) : 0);
  }
  function topSummary(payload, lanes) {
    var list = Array.isArray(lanes) ? lanes : [];
    var raw = (payload && payload.summary) || {};
    var runtime = (payload && payload.runtime && payload.runtime.session_runtime) || {};
    var laneRuntime = (payload && payload.lane_runtime) || {};
    return {
      enabled_lanes: asCount(raw.enabled_lanes, list.filter(function (lane) { return !!lane.enabled; }).length),
      tracked: asCount(raw.tracked, Object.keys(laneRuntime).length),
      sessions: asCount(raw.sessions, runtime && typeof runtime === "object" ? Object.keys(runtime).length : 0),
      disabled: asCount(raw.disabled, list.filter(function (lane) { return !lane.enabled; }).length)
    };
  }
  function TopSummary(props) {
    var item = props.summary || {};
    return h("p", { className: "lin-panel__path" },
      "enabled " + asCount(item.enabled_lanes, 0) +
      " / disabled " + asCount(item.disabled, 0) +
      " / tracked " + asCount(item.tracked, 0) +
      " / sessions " + asCount(item.sessions, 0)
    );
  }
  function NameCheckboxPicker(props) {
    var available = Array.isArray(props.available) ? props.available : [];
    var selected = Array.isArray(props.selected) ? props.selected : [];
    var names = available.map(function (item) { return String(item.name || ""); });
    var orphaned = selected.filter(function (name) { return names.indexOf(name) < 0; }).map(function (name) { return { name: name, description: "" }; });
    var all = orphaned.concat(available);
    if (!all.length) return h("p", { className: "lin-panel__hint" }, props.emptyLabel || "No items available.");
    function toggle(name, checked) {
      if (checked && selected.indexOf(name) < 0) props.onChange(selected.concat([name]));
      else if (!checked) props.onChange(selected.filter(function (item) { return item !== name; }));
    }
    return h("div", { id: props.id, className: "lin-panel__textarea", style: { maxHeight: "9rem", overflowY: "auto", minHeight: "0", padding: "0.25rem" } },
      all.map(function (item) {
        var name = String(item.name || "");
        return h("label", { key: name, title: item.description || undefined, className: "lin-panel__fieldRowCheckbox", style: { padding: "0.25rem 0.35rem" } },
          h("input", { type: "checkbox", className: "accent-foreground", checked: selected.indexOf(name) >= 0, onChange: function (e) { toggle(name, !!e.target.checked); } }),
          h("span", { className: "font-mono-ui truncate" }, name)
        );
      })
    );
  }
  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }
  function formatTimestamp(value) {
    var text = String(value || "").trim();
    if (!text) return "(never)";
    return text;
  }
  function formatMinutesAgo(value, timestamp) {
    var seconds = NaN;
    if (timestamp) {
      var parsed = Date.parse(String(timestamp));
      if (Number.isFinite(parsed)) seconds = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
    }
    if (!Number.isFinite(seconds)) {
      var n = Number(value);
      if (Number.isFinite(n)) seconds = Math.max(0, Math.floor(n * 60));
    }
    if (!Number.isFinite(seconds)) return "(never)";
    if (seconds < 60) return String(Math.max(0, seconds)) + "s ago";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return String(minutes) + "m ago";
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return String(hours) + "h ago";
    return String(Math.floor(hours / 24)) + "d ago";
  }
  function activeProfile(payload) {
    try {
      var fromUrl = new URLSearchParams(window.location.search || "").get("profile");
      if (fromUrl !== null) return String(fromUrl || "default").trim() || "default";
    } catch (_e) {}
    return String((payload && payload.active_profile) || "default").trim() || "default";
  }
  function profilePatternsMatch(profile, patterns) {
    var list = Array.isArray(patterns) ? patterns.map(function (v) { return String(v || "").trim(); }).filter(Boolean) : [];
    if (!list.length) list = ["default"];
    var p = String(profile || "default").trim() || "default";
    return list.some(function (item) {
      if (["*", "all", "any"].includes(item.toLowerCase())) return false;
      return item === p || item.toLowerCase() === p.toLowerCase();
    });
  }
  function laneMatchesActiveProfile(lane, payload) {
    var profile = activeProfile(payload);
    if (!profilePatternsMatch(profile, lane && lane.target_profiles)) return false;
    var excludes = Array.isArray(lane && lane.exclude_profiles) ? lane.exclude_profiles : [];
    return !(excludes.length && profilePatternsMatch(profile, excludes));
  }
  function defaultLane(index) {
    const n = (index || 0) + 1;
    return {
      name: "memory-" + n,
      enabled: true,
      prompt: "",
      include_current_time: false,
      include_current_source: false,
      include_memory_recall_guidance: false,
      idle_seconds: 0,
      reinject_interval_minutes: 0,
      target_sessions: [],
      target_profiles: ["default"],
      exclude_sessions: [],
      exclude_profiles: [],
      skills: [],
      snapshot_files: []
    };
  }
  function defaultScopeMode(lane) {
    const sessions = Array.isArray(lane && lane.target_sessions) ? lane.target_sessions.filter(function (item) { return item !== "*"; }) : [];
    const excludeSessions = Array.isArray(lane && lane.exclude_sessions) ? lane.exclude_sessions : [];
    if (sessions.length) return "target";
    if (excludeSessions.length) return "exclude";
    return "all";
  }
  function scopeSummaryParts(lane) {
    var targets = Array.isArray(lane && lane.target_sessions)
      ? lane.target_sessions.map(function (item) { return String(item || "").trim(); }).filter(function (item) { return item && item !== "*"; })
      : [];
    var excludes = Array.isArray(lane && lane.exclude_sessions)
      ? lane.exclude_sessions.map(function (item) { return String(item || "").trim(); }).filter(Boolean)
      : [];
    var parts = [];
    if (targets.length) parts.push("対象 · " + truncate(targets.join(", "), 96));
    else if (excludes.length) parts.push("除外指定のみ");
    else parts.push("全対象");
    if (excludes.length) parts.push("除外 · " + truncate(excludes.join(", "), 96));
    return parts;
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
      view: "list",
      availableSkills: []
    });
    const laneEpochRef = React.useRef(0);
    const configRequestSeqRef = React.useRef(0);
    const activeLaneRef = React.useRef(null);

    useEffect(function () {
      activeLaneRef.current = state.selectedLaneName || null;
    }, [state.selectedLaneName]);

    const syncForm = useCallback(function (payload, desiredLaneName) {
      const config = (payload && payload.config) || { lanes: [] };
      const lanes = Array.isArray(config.lanes) ? config.lanes : [];
      const visibleLanes = lanes.filter(function (item) { return laneMatchesActiveProfile(item, payload); });
      const selectedName = desiredLaneName || (visibleLanes[0] && visibleLanes[0].name) || null;
      const lane = visibleLanes.find(function (item) { return String(item.name) === String(selectedName); }) || visibleLanes[0] || defaultLane(0);
      setState(function (prev) {
        return Object.assign({}, prev, {
          payload: payload,
          selectedLaneName: lane.name || selectedName,
          form: {
            name: String(lane.name || ""),
            enabled: !!lane.enabled,
            promptText: String(lane.prompt || ""),
            skills: Array.isArray(lane.skills) ? lane.skills.slice() : [],
            includeCurrentTime: !!lane.include_current_time,
            includeCurrentSource: !!lane.include_current_source,
            includeMemoryRecallGuidance: !!lane.include_memory_recall_guidance,
            dailyMemoryRoot: String(config.daily_memory_root || "/opt/data/workspace/diaries"),
            scopeMode: defaultScopeMode(lane),
            targetSessionsText: ((lane.target_sessions || []).filter(function (item) { return item !== "*"; })).join("\n"),
            targetProfile: activeProfile(payload),
            excludeSessionsText: ((lane.exclude_sessions || [])).join("\n"),
            snapshotFilesText: ((lane.snapshot_files || [])).join("\n")
          }
        });
      });
    }, []);

    const load = useCallback(function (desiredLaneName) {
      const laneEpoch = laneEpochRef.current;
      const requestSeq = ++configRequestSeqRef.current;
      const fallbackLaneName = desiredLaneName || activeLaneRef.current;
      setState(function (prev) { return Object.assign({}, prev, { loading: true, error: "" }); });
      Promise.all([
        api("/config"),
        SDK.fetchJSON("/api/skills").catch(function () { return []; })
      ]).then(function (rows) {
        if (requestSeq !== configRequestSeqRef.current) return;
        var payload = rows[0];
        var skills = Array.isArray(rows[1]) ? rows[1].slice().sort(function (a, b) { return String(a.name || "").localeCompare(String(b.name || "")); }) : [];
        setState(function (prev) { return Object.assign({}, prev, { loading: false, payload: payload, availableSkills: skills }); });
        if (laneEpoch !== laneEpochRef.current) return;
        syncForm(payload, fallbackLaneName || activeLaneRef.current);
      }).catch(function (err) {
        if (requestSeq !== configRequestSeqRef.current) return;
        setState(function (prev) { return Object.assign({}, prev, { loading: false, error: parseApiErrorMessage(err) }); });
      });
    }, [syncForm]);

    useEffect(function () { load(); }, [load]);

    function setFormValue(key, value) {
      setState(function (prev) { return Object.assign({}, prev, { form: Object.assign({}, prev.form || {}, { [key]: value }) }); });
    }
    function currentScopeTextKey() {
      var mode = String((state.form && state.form.scopeMode) || "all");
      return mode === "exclude" ? "excludeSessionsText" : "targetSessionsText";
    }
    function currentScopeLabel() {
      var mode = String((state.form && state.form.scopeMode) || "all");
      if (mode === "target") return "target values";
      if (mode === "exclude") return "exclude values";
      return "values";
    }
    function currentScopePlaceholder() {
      var mode = String((state.form && state.form.scopeMode) || "all");
      if (mode === "all") return "scope is all sessions; no input needed";
      return "one session selector per line";
    }
    function currentConfig() {
      return (state.payload && state.payload.config) || { schema_version: 1, description: "memory dashboard v3 config", daily_memory_root: "/opt/data/workspace/diaries", lanes: [] };
    }
    function currentLanes() {
      return Array.isArray(currentConfig().lanes) ? currentConfig().lanes : [];
    }
    function visibleLanes() {
      return currentLanes().filter(function (lane) { return laneMatchesActiveProfile(lane, state.payload); });
    }
    function currentLane() {
      const lanes = visibleLanes();
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
    function buildLanePayload() {
      const form = state.form || {};
      const scopeMode = String(form.scopeMode || "all");
      const scopeValues = scopeMode === "all" ? [] : splitLines(form[currentScopeTextKey()]);
      const useTarget = scopeMode === "target" && scopeValues.length > 0;
      const useExclude = scopeMode === "exclude" && scopeValues.length > 0;
      return {
        name: String(form.name || "").trim(),
        enabled: !!form.enabled,
        prompt: String(form.promptText || "").trim(),
        skills: Array.isArray(form.skills) ? form.skills.slice() : [],
        include_current_time: !!form.includeCurrentTime,
        include_current_source: !!form.includeCurrentSource,
        include_memory_recall_guidance: !!form.includeMemoryRecallGuidance,
        idle_seconds: 0,
        reinject_interval_minutes: 0,
        target_sessions: useTarget ? scopeValues : [],
        target_profiles: [activeProfile(state.payload)],
        exclude_sessions: useExclude ? scopeValues : [],
        exclude_profiles: [],
        snapshot_files: splitLines(form.snapshotFilesText)
      };
    }
    function buildConfigPayloadFromSelectedLane() {
      const config = clone(currentConfig());
      config.schema_version = 1;
      config.description = String(config.description || "memory dashboard v3 config");
      config.daily_memory_root = String((state.form && state.form.dailyMemoryRoot) || config.daily_memory_root || "/opt/data/workspace/diaries").trim() || "/opt/data/workspace/diaries";
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
      const requestSeq = ++configRequestSeqRef.current;
      const targetLaneName = syncLaneName || activeLaneRef.current;
      setState(function (prev) { return Object.assign({}, prev, { saving: true, loading: false, error: "", banner: "" }, nextState || {}); });
      api("/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then(function (nextPayload) {
        if (requestSeq !== configRequestSeqRef.current) return;
        var wakeInfo = nextPayload && nextPayload.watcher ? (" · watcher wake " + String(nextPayload.watcher.woken_watchers || 0)) : "";
        var laneMoved = laneEpoch !== laneEpochRef.current;
        setState(function (prev) {
          var baseState = { saving: false, loading: false, banner: successMessage + wakeInfo, payload: nextPayload };
          if (laneMoved) return Object.assign({}, prev, baseState);
          return Object.assign({}, prev, Object.assign({}, baseState, nextState || {}));
        });
        if (laneMoved) return;
        syncForm(nextPayload, targetLaneName || activeLaneRef.current);
      }).catch(function (err) {
        if (requestSeq !== configRequestSeqRef.current) return;
        setState(function (prev) { return Object.assign({}, prev, { saving: false, loading: false, error: parseApiErrorMessage(err) }); });
      });
    }
    function save() {
      var payload;
      var selected;
      var nextLaneName;
      try {
        payload = buildConfigPayloadFromSelectedLane();
        selected = payload.lanes.find(function (lane) { return String(lane.name) === String((state.form && state.form.name) || state.selectedLaneName); });
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
      var nextIndex = lanes.length;
      var lane = Object.assign({}, defaultLane(nextIndex), { target_profiles: [activeProfile(state.payload)] });
      var usedNames = new Set(lanes.map(function (item) { return String(item.name); }));
      while (usedNames.has(lane.name)) {
        nextIndex += 1;
        lane = Object.assign({}, defaultLane(nextIndex), { target_profiles: [activeProfile(state.payload)] });
      }
      var payload = clone(currentConfig());
      payload.lanes = lanes.concat([lane]);
      persistConfig(payload, "Memory added", { view: "detail", selectedLaneName: lane.name }, lane.name);
    }
    function deleteCurrentLane() {
      var lanes = currentLanes();
      if (lanes.length <= 1) {
        setState(function (prev) { return Object.assign({}, prev, { error: "最後の memory は消せないよ", banner: "" }); });
        return;
      }
      var current = currentLane();
      if (!current) return;
      if (typeof window !== "undefined" && window.confirm && !window.confirm("Delete memory '" + current.name + "'?")) return;
      var payload = clone(currentConfig());
      payload.lanes = lanes.filter(function (lane) { return String(lane.name) !== String(current.name); });
      var nextSelected = payload.lanes[0] && payload.lanes[0].name;
      persistConfig(payload, "Memory deleted", { view: "list", selectedLaneName: nextSelected || null }, nextSelected || null);
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

    function bulkPolicyValue(key) {
      var list = visibleLanes();
      if (!list.length) return false;
      return list.every(function (item) { return !!item[key]; });
    }
    function bulkPolicyMixed(key) {
      var list = visibleLanes();
      if (!list.length) return false;
      var enabledCount = list.filter(function (item) { return !!item[key]; }).length;
      return enabledCount > 0 && enabledCount < list.length;
    }
    function setBulkInjectionPolicy(key, enabled) {
      var payload = clone(currentConfig());
      payload.daily_memory_root = String((state.form && state.form.dailyMemoryRoot) || payload.daily_memory_root || "/opt/data/workspace/diaries").trim() || "/opt/data/workspace/diaries";
      var visibleNames = new Set(visibleLanes().map(function (lane) { return String(lane.name); }));
      var lanes = Array.isArray(payload.lanes) ? payload.lanes.slice() : [];
      payload.lanes = lanes.map(function (lane) {
        if (!visibleNames.has(String(lane.name))) return lane;
        var next = Object.assign({}, lane);
        next[key] = !!enabled;
        return next;
      });
      persistConfig(payload, enabled ? "Injection policy enabled" : "Injection policy disabled", { view: "list" });
    }
    function saveDailyMemoryRoot() {
      var payload = clone(currentConfig());
      payload.schema_version = 1;
      payload.description = String(payload.description || "memory dashboard v3 config");
      payload.daily_memory_root = String((state.form && state.form.dailyMemoryRoot) || payload.daily_memory_root || "/opt/data/workspace/diaries").trim() || "/opt/data/workspace/diaries";
      persistConfig(payload, "Daily memory root saved", { view: "list" });
    }

    var payload = state.payload || {};
    var form = state.form || {};
    var lanes = visibleLanes();
    var lane = currentLane();

    function renderList() {
      var summary = topSummary(payload, lanes);
      return h("div", { className: "lin-panel" },
        h("div", { className: "lin-panel__topActions" },
          h(Pill, { tone: "good" }, String(lanes.length) + " memory setting" + (lanes.length === 1 ? "" : "s")),
          h(Button, { type: "button", onClick: createLane }, state.saving ? "Saving..." : "New setting")
        ),
        h(Card, { className: "lin-panel__hero" },
          h(CardContent, { className: "lin-panel__heroContent" },
            h("p", { className: "lin-panel__lead" }, "Memory injection の設定を管理する画面です。一覧でシステムプロンプトへ入れる共通方針を決め、個別設定では対象セッション、差し込むファイル、skills を編集できます。"),
            h(TopSummary, { summary: summary }),
            payload.config_file ? h("p", { className: "lin-panel__path" }, "config: " + payload.config_file) : null,
            state.error ? h("p", { className: "lin-panel__error" }, state.error) : null,
            state.banner ? h("p", { className: "lin-panel__banner" }, state.banner) : null
          )
        ),
        h(Card, { className: "lin-panel__card lin-panel__policyCard" },
          h(CardHeader, null, h(CardTitle, null, "System prompt injection policy")),
          h(CardContent, { className: "lin-panel__policyGrid" },
            h("label", { className: "lin-panel__fieldRowCheckbox" },
              h(Checkbox, { checked: bulkPolicyValue("include_current_time"), disabled: !!state.saving || !lanes.length, onCheckedChange: function (v) { setBulkInjectionPolicy("include_current_time", !!v); } }),
              h("span", null, "current time"),
              bulkPolicyMixed("include_current_time") ? h(Pill, { tone: "muted" }, "mixed") : null
            ),
            h("label", { className: "lin-panel__fieldRowCheckbox" },
              h(Checkbox, { checked: bulkPolicyValue("include_current_source"), disabled: !!state.saving || !lanes.length, onCheckedChange: function (v) { setBulkInjectionPolicy("include_current_source", !!v); } }),
              h("span", null, "current source"),
              bulkPolicyMixed("include_current_source") ? h(Pill, { tone: "muted" }, "mixed") : null
            ),
            h("label", { className: "lin-panel__fieldRowCheckbox" },
              h(Checkbox, { checked: bulkPolicyValue("include_memory_recall_guidance"), disabled: !!state.saving || !lanes.length, onCheckedChange: function (v) { setBulkInjectionPolicy("include_memory_recall_guidance", !!v); } }),
              h("span", null, "memory_search / memory_get guidance"),
              bulkPolicyMixed("include_memory_recall_guidance") ? h(Pill, { tone: "muted" }, "mixed") : null
            ),
            h("div", { className: "lin-panel__field", style: { gridColumn: "1 / -1" } },
              h(Label, null, "daily memory root"),
              h(Input, { className: "lin-panel__input", value: form.dailyMemoryRoot || "/opt/data/workspace/diaries", onChange: function (e) { setFormValue("dailyMemoryRoot", e.target.value); }, placeholder: "/opt/data/workspace/diaries" }),
              h("div", { className: "lin-panel__buttonRow" },
                h(Button, { type: "button", onClick: saveDailyMemoryRoot, disabled: !!state.saving }, state.saving ? "Saving..." : "Save daily memory root")
              ),
              h("p", { className: "lin-panel__hint" }, "memory_search / memory_get が読む diary / daily memory の場所です。相対パスは memory plugin root 基準です。")
            ),
            h("p", { className: "lin-panel__hint lin-panel__policyHint" }, "この3つは現在の profile に見えている memory 設定へ一括で適用されます。daily memory root は config 全体の共通設定です。")
          )
        ),
        h("div", { className: "lin-panel__list" },
          lanes.map(function (item) {
            var files = Array.isArray(item.snapshot_files) ? item.snapshot_files : [];
            var runtimeInfo = laneRuntime(item.name) || {};
            var lastRunLabel = formatMinutesAgo(runtimeInfo.last_applied_minutes_ago, runtimeInfo.last_applied_at);
            return h(Card, { key: item.name, className: "lin-panel__laneCard" },
              h(CardContent, { className: "lin-panel__laneBody" },
                h("div", { className: "lin-panel__laneMain" },
                  h("div", { className: "lin-panel__laneTitleRow" },
                    h("div", null,
                      h("div", { className: "lin-panel__laneTitle" }, String(item.name || "memory"))
                    ),
                    h("div", { className: "lin-panel__titleMeta" },
                      h(Pill, { tone: "good" }, lastRunLabel),
                      h("label", { className: "lin-panel__fieldRowCheckbox" },
                        h(Checkbox, { checked: !!item.enabled, disabled: !!state.saving, onCheckedChange: function (v) { toggleLaneEnabled(item.name, !!v); } }),
                        h("span", null, item.enabled ? "enabled" : "disabled")
                      )
                    )
                  ),
                  h("div", { className: "lin-panel__laneMeta" },
                    scopeSummaryParts(item).map(function (part) { return h("span", { key: "scope-" + part }, part); }),
                    h("span", null, "skills · " + ((item.skills || []).join(", ") || "(none)")),
                    h("span", null, "current time · " + (item.include_current_time ? "inject" : "skip")),
                    h("span", null, "current source · " + (item.include_current_source ? "inject" : "skip")),
                    h("span", null, "recall guidance · " + (item.include_memory_recall_guidance ? "inject" : "skip")),
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
      var summaryTargetKind = "session";
      var summaryScopeMode = String(form.scopeMode || "all");
      var summaryScopeValues = summaryScopeMode === "target"
        ? splitLines(form.targetSessionsText)
        : (summaryScopeMode === "exclude" ? splitLines(form.excludeSessionsText) : []);
      if (!summaryScopeValues.length) summaryScopeMode = "all";
      var summaryTargetText = summaryScopeMode === "target" ? summaryScopeValues.join(", ") : "(all)";
      var summaryExcludeText = summaryScopeMode === "exclude" ? summaryScopeValues.join(", ") : "(none)";
      var summaryTargetProfiles = activeProfile(state.payload);
      var summaryCurrentTime = form.includeCurrentTime ? "inject" : "skip";
      var summaryCurrentSource = form.includeCurrentSource ? "inject" : "skip";
      var summaryRecallGuidance = form.includeMemoryRecallGuidance ? "inject" : "skip";
      var summarySkills = Array.isArray(form.skills) && form.skills.length ? form.skills.join(", ") : "(none)";
      var runtimeInfo = laneRuntime(form.name) || {};
      var previewInfo = lanePreview(form.name) || {};
      var summary = topSummary(payload, lanes);
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
            h("p", { className: "lin-panel__lead" }, "選択した memory 設定の詳細です。対象範囲、snapshot files、事前ロードする skills を編集できます。システムプロンプト注入方針は一覧画面で一括変更します。"),
            h(TopSummary, { summary: summary }),
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
              h("div", { className: "lin-panel__field" }, h(Label, null, "name"), h(Input, { className: "lin-panel__input", value: form.name || "", onChange: function (e) { setFormValue("name", e.target.value); }, placeholder: "setting name" }), h("p", { className: "lin-panel__hint" }, "この設定は、今開いている dashboard profile（" + activeProfile(state.payload) + "）だけに保存されるよ。")),
              h("div", { className: "lin-panel__field" }, h(Label, null, "prompt"), h(Textarea, { className: "lin-panel__textarea", value: form.promptText || "", onChange: function (e) { setFormValue("promptText", e.target.value); }, placeholder: "Optional guidance for this setting" }), h("p", { className: "lin-panel__hint" }, "snapshot file とは別に、この lane 専用の補助 prompt を memory injection へ積めるよ。")),
              h("div", { className: "lin-panel__field" },
                h(Label, null, "Skills (optional)"),
                h(NameCheckboxPicker, { id: "memory-skills", available: state.availableSkills || [], selected: form.skills || [], onChange: function (skills) { setFormValue("skills", skills); }, emptyLabel: "No skills installed for this profile." }),
                h("p", { className: "lin-panel__hint" }, "Selected skills are loaded before this memory lane is injected — the lane sets when, the skill sets how.")
              ),
              h("div", { className: "lin-panel__field" }, h(Label, null, "scope"), h(SelectField, { value: form.scopeMode || "all", onChange: function (v) { setFormValue("scopeMode", v || "all"); }, options: [
                { value: "all", label: "全て" },
                { value: "target", label: "対象" },
                { value: "exclude", label: "除外" }
              ] })),
              h("div", { className: "lin-panel__field" }, h(Label, null, currentScopeLabel()), h(Textarea, { className: "lin-panel__textarea", disabled: String(form.scopeMode || "all") === "all", value: String(form.scopeMode || "all") === "all" ? "" : (form[currentScopeTextKey()] || ""), onChange: function (e) { setFormValue(currentScopeTextKey(), e.target.value); }, placeholder: currentScopePlaceholder() })),
              h("div", { className: "lin-panel__field" }, h(Label, null, "snapshot files"), h(Textarea, { className: "lin-panel__textarea", value: form.snapshotFilesText || "", onChange: function (e) { setFormValue("snapshotFilesText", e.target.value); }, placeholder: "/path/to/snapshot.md" })),
              h("div", { className: "lin-panel__buttonRow" },
                h(Button, { type: "button", onClick: save }, state.saving ? "Saving..." : "Save"),
                h(Button, { type: "button", onClick: deleteCurrentLane }, state.saving ? "Working..." : "Delete")
              )
            )
          ),
          h(Card, { className: "lin-panel__card" },
            h(CardHeader, null, h(CardTitle, null, "Summary / preview")),
            h(CardContent, { className: "lin-panel__content" },
              h("div", { className: "lin-panel__summary" },
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "prompt"), h("dd", null, promptPreview(form.promptText))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "last run"), h("dd", null, formatMinutesAgo(runtimeInfo.last_applied_minutes_ago, runtimeInfo.last_applied_at))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "last reason"), h("dd", null, String(runtimeInfo.last_decision_reason || "(none)"))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "matched sessions"), h("dd", null, String(runtimeInfo.matched_session_count || 0))),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "skills"), h("dd", null, summarySkills)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "current time"), h("dd", null, summaryCurrentTime)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "current source"), h("dd", null, summaryCurrentSource)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "recall guidance"), h("dd", null, summaryRecallGuidance)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "daily memory root"), h("dd", null, form.dailyMemoryRoot || "/opt/data/workspace/diaries")),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "target"), h("dd", null, summaryTargetKind + " · " + summaryTargetText)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "exclude"), h("dd", null, summaryTargetKind + " · " + summaryExcludeText)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "dashboard profile"), h("dd", null, summaryTargetProfiles)),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "files"), h("dd", null, splitLines(form.snapshotFilesText).join(", ") || "(none)"))
              ),
              h("div", { className: "lin-panel__summary" },
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "preview"), h("dd", null, previewInfo.has_preview ? "ready" : "(none)")),
                h("div", { className: "lin-panel__summaryRow" }, h("dt", null, "source session"), h("dd", null, String(runtimeInfo.last_session_key || "(none)")))
              ),
              h("pre", { className: "lin-panel__textarea lin-panel__preview", style: { whiteSpace: "pre-wrap" } }, String(previewInfo.text || "(preview empty)"))
            )
          )
        )
      );
    }

    return state.view === "detail" && lane ? renderDetail() : renderList();
  }

  window.__HERMES_PLUGINS__.register("memory", Page);
})();
