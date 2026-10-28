window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {
var module = { exports: {} }; var exports = module.exports;
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/plugin/client/index.jsx
var index_exports = {};
__export(index_exports, {
  apply: () => apply,
  inject: () => inject
});
module.exports = __toCommonJS(index_exports);
var React = __toESM(require("react"), 1);

// src/plugin/shared/settings.js
var SETTINGS_NAMESPACE = "coderag";
var BUNDLE_NAME = "dsh-coderag";
var ROW_CONFIG_KEY = `${BUNDLE_NAME}#${SETTINGS_NAMESPACE}`;
var DEFAULT_VALUES = Object.freeze({
  root: "",
  maxFiles: 0,
  maxFileBytes: 0,
  maxTokens: 0,
  extraExtensions: "",
  semantic: false,
  semanticBackend: "",
  semanticUrl: "",
  semanticModel: "",
  semanticTimeout: 0,
  semanticBatch: 0,
  semanticMaxChunks: 0,
  semanticAllowRemote: false
});
var SEMANTIC_BACKENDS = Object.freeze(["", "ollama", "openai"]);
var ENGINE_DEFAULTS = Object.freeze({
  maxFiles: 2e4,
  maxFileBytes: 1048576,
  maxTokens: 4e3,
  semanticTimeout: 30,
  semanticBatch: 16,
  semanticMaxChunks: 1e5,
  semanticUrl: "http://127.0.0.1:11434",
  semanticModel: "bge-m3"
});
var FIELDS = Object.freeze([
  Object.freeze({
    key: "root",
    group: "workspace",
    kind: "text",
    label: "工作区根",
    env: "CODERAG_ROOT",
    placeholder: "例如 F:\\Projects\\my-repo",
    hint: "引擎要索引的目录。留空时引擎以 WORKSPACE_INVALID 明确报错，不会猜目录。"
  }),
  Object.freeze({
    key: "maxFiles",
    group: "index",
    kind: "integer",
    label: "文件数量上限",
    env: "CODERAG_MAX_FILES",
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.maxFiles}）。达到上限会显式失败并报告实际数量，不静默截断。`
  }),
  Object.freeze({
    key: "maxFileBytes",
    group: "index",
    kind: "integer",
    label: "单文件字节上限",
    env: "CODERAG_MAX_FILE_BYTES",
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.maxFileBytes}）。超过上限的文件计入 skipped.too_large。`
  }),
  Object.freeze({
    key: "maxTokens",
    group: "index",
    kind: "integer",
    label: "检索 token 预算",
    env: "CODERAG_MAX_TOKENS",
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.maxTokens}）。这个名字含 TOKEN，历史配置里无法从继承环境传下来，所以由设置行显式接管。`
  }),
  Object.freeze({
    key: "extraExtensions",
    group: "index",
    kind: "text",
    label: "额外文件扩展名",
    env: "CODERAG_EXTRA_EXTENSIONS",
    placeholder: "例如 .mxml,.as",
    hint: "逗号或空格分隔，只增不减：内置白名单不能移除，密钥文件黑名单仍然生效。"
  }),
  Object.freeze({
    key: "semantic",
    group: "semantic",
    kind: "boolean",
    label: "启用语义检索",
    env: "CODERAG_SEMANTIC",
    hint: "默认关闭，关闭时完全走 BM25，不联网、不读向量 sidecar。"
  }),
  Object.freeze({
    key: "semanticBackend",
    group: "semantic",
    kind: "select",
    label: "语义后端",
    env: "CODERAG_SEMANTIC_BACKEND",
    options: Object.freeze([
      Object.freeze({ value: "", label: "未设置（引擎默认 ollama）" }),
      Object.freeze({ value: "ollama", label: "ollama（本地，仅 loopback）" }),
      Object.freeze({ value: "openai", label: "openai（云端，需显式 URL/模型）" })
    ]),
    hint: "云端后端会把已入库 chunk 文本（含工作区相对路径与符号名）发往所配服务。"
  }),
  Object.freeze({
    key: "semanticUrl",
    group: "semantic",
    kind: "text",
    label: "语义服务 URL",
    env: "CODERAG_SEMANTIC_URL",
    placeholder: ENGINE_DEFAULTS.semanticUrl,
    hint: "本地后端只允许 loopback；云端后端建议 https。"
  }),
  Object.freeze({
    key: "semanticModel",
    group: "semantic",
    kind: "text",
    label: "语义模型",
    env: "CODERAG_SEMANTIC_MODEL",
    placeholder: ENGINE_DEFAULTS.semanticModel,
    hint: "本地默认 bge-m3；云端后端必须显式给出。"
  }),
  Object.freeze({
    key: "semanticTimeout",
    group: "semantic",
    kind: "integer",
    label: "语义请求超时（秒）",
    env: "CODERAG_SEMANTIC_TIMEOUT",
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.semanticTimeout} 秒）。`
  }),
  Object.freeze({
    key: "semanticBatch",
    group: "semantic",
    kind: "integer",
    label: "语义批量大小",
    env: "CODERAG_SEMANTIC_BATCH",
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.semanticBatch}）。`
  }),
  Object.freeze({
    key: "semanticMaxChunks",
    group: "semantic",
    kind: "integer",
    label: "向量化 chunk 上限",
    env: "CODERAG_SEMANTIC_MAX_CHUNKS",
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.semanticMaxChunks}）。首次云端索引会按此上限一次性计费，达到上限即停止。`
  }),
  Object.freeze({
    key: "semanticAllowRemote",
    group: "semantic",
    kind: "boolean",
    label: "允许非 loopback 云端地址",
    env: "CODERAG_SEMANTIC_ALLOW_REMOTE",
    envTrue: "1",
    hint: "只有「语义检索开启 + openai 后端 + 非 loopback URL」时才需要打开；否则引擎会拒绝启用云端后端。"
  })
]);
var GROUPS = Object.freeze([
  Object.freeze({ id: "workspace", title: "工作区", description: "决定索引哪个目录。" }),
  Object.freeze({ id: "index", title: "索引范围", description: "控制收录哪些文件、最多收录多少。" }),
  Object.freeze({ id: "semantic", title: "语义检索（可选）", description: "默认关闭；关闭时完全走 BM25。" })
]);
var EXTENSION_TOKEN = /^[A-Za-z0-9][A-Za-z0-9_+-]*$/;
var FIELD_BY_KEY = new Map(FIELDS.map((field) => [field.key, field]));
var INTEGER_KEYS = /* @__PURE__ */ new Set(["maxFiles", "maxFileBytes", "maxTokens", "semanticTimeout", "semanticBatch", "semanticMaxChunks"]);
function normalizeValue(key, value) {
  if (FIELD_BY_KEY.get(key)?.kind === "boolean") return value === true;
  if (INTEGER_KEYS.has(key)) {
    const number = Math.floor(Number(value));
    return Number.isFinite(number) && number > 0 ? number : 0;
  }
  if (typeof value === "string") return value.trim();
  return value === void 0 || value === null ? "" : String(value);
}
function normalizeValues(values = {}) {
  const source = values !== null && typeof values === "object" ? values : {};
  const result = {};
  for (const field of FIELDS) {
    const raw = Object.hasOwn(source, field.key) ? source[field.key] : DEFAULT_VALUES[field.key];
    result[field.key] = normalizeValue(field.key, raw);
  }
  return result;
}
function validateValues(values) {
  const draft = values !== null && typeof values === "object" ? values : {};
  const errors = [];
  const reject = (field, message) => errors.push({ field, message });
  for (const key of ["maxFiles", "maxFileBytes", "maxTokens", "semanticTimeout", "semanticBatch", "semanticMaxChunks"]) {
    const raw = Object.hasOwn(draft, key) ? draft[key] : DEFAULT_VALUES[key];
    const text = typeof raw === "string" ? raw.trim() : String(raw);
    if (text === "") continue;
    if (!/^(0|[1-9][0-9]*)$/.test(text)) reject(key, "需要 0 或正整数（0 = 引擎默认）。");
  }
  const extensions = String(draft.extraExtensions ?? "").trim();
  if (extensions !== "") {
    for (const token of extensions.split(/[\s,]+/).filter(Boolean)) {
      const bare = token.startsWith(".") ? token.slice(1) : token;
      if (!EXTENSION_TOKEN.test(bare)) {
        reject("extraExtensions", `"${token}" 不是简单扩展名：不能含点、路径分隔符或通配符（例如 .mxml,.as）。`);
        break;
      }
    }
  }
  const backend = String(draft.semanticBackend ?? "").trim();
  if (!SEMANTIC_BACKENDS.includes(backend)) reject("semanticBackend", "只支持 未设置 / ollama / openai。");
  const url = String(draft.semanticUrl ?? "").trim();
  const urlWellFormed = url === "" || /^https?:\/\/[^\s]+$/i.test(url);
  if (!urlWellFormed) reject("semanticUrl", "需要以 http:// 或 https:// 开头的地址。");
  const loopbackUrl = url !== "" && /^https?:\/\/(?:127(?:\.\d+){3}|localhost|\[::1\])(?::\d+)?(?:\/|$)/i.test(url);
  if (url !== "" && urlWellFormed && backend === "ollama" && !loopbackUrl) {
    reject("semanticUrl", "ollama 后端只允许 loopback 地址（127.0.0.1 / localhost / [::1]）。");
  }
  const allowRemote = draft.semanticAllowRemote === true;
  if (draft.semantic === true && backend === "openai") {
    if (url === "") reject("semanticUrl", "云端 openai 后端必须显式给出 URL。");
    if (String(draft.semanticModel ?? "").trim() === "") {
      reject("semanticModel", "云端 openai 后端必须显式给出模型名。");
    }
    if (url !== "" && urlWellFormed && !loopbackUrl && !allowRemote) {
      reject("semanticAllowRemote", "该云端地址不是 loopback；请打开「允许非 loopback 云端地址」，否则引擎拒绝启用云端后端。");
    }
  }
  return errors;
}

// src/plugin/shared/client-form.js
function toDraft(values) {
  const normalized = normalizeValues(values);
  const draft = {};
  for (const field of FIELDS) {
    draft[field.key] = field.kind === "boolean" ? normalized[field.key] === true : String(normalized[field.key]);
  }
  return draft;
}
function toValue(field, raw) {
  if (field.kind === "boolean") return raw === true;
  if (field.kind === "integer") {
    const number = Math.floor(Number(raw));
    return Number.isFinite(number) && number > 0 ? number : 0;
  }
  return String(raw ?? "");
}
function draftKey(draft) {
  return JSON.stringify(FIELDS.map((field) => [field.key, draft[field.key]]));
}
function buildSetOps(draft) {
  return FIELDS.map((field) => ({ op: "set", path: [field.key], value: toValue(field, draft[field.key]) }));
}

// src/plugin/client/index.jsx
var import_jsx_runtime = require("react/jsx-runtime");
var inject = ["slots", "configForms"];
var { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } = React;
var SAVED_NOTICE_MS = 4e3;
var styles = {
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    color: "var(--dsw-alias-label-primary, #1f2328)",
    fontSize: "13px",
    lineHeight: 1.5
  },
  header: { display: "flex", flexDirection: "column", gap: "4px" },
  title: { margin: 0, fontSize: "15px", fontWeight: 600 },
  group: {
    border: "1px solid var(--dsw-alias-border-secondary, #d0d7de)",
    borderRadius: "8px",
    padding: "12px 14px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    margin: 0
  },
  legend: { fontWeight: 600, padding: "0 4px" },
  description: { margin: 0, opacity: 0.75 },
  field: { display: "flex", flexDirection: "column", gap: "4px" },
  labelRow: { display: "flex", alignItems: "center", gap: "8px", fontWeight: 500 },
  control: {
    boxSizing: "border-box",
    width: "100%",
    padding: "6px 8px",
    borderRadius: "6px",
    border: "1px solid var(--dsw-alias-border-secondary, #d0d7de)",
    background: "var(--dsw-alias-bg-primary, #ffffff)",
    color: "inherit",
    fontSize: "13px"
  },
  hint: { margin: 0, fontSize: "12px", opacity: 0.72 },
  error: { margin: 0, fontSize: "12px", color: "var(--dsw-alias-label-danger, #cf222e)" },
  actions: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" },
  button: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid var(--dsw-alias-border-secondary, #d0d7de)",
    background: "var(--dsw-alias-bg-primary, #ffffff)",
    color: "inherit",
    fontSize: "13px",
    cursor: "pointer"
  },
  primary: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid transparent",
    background: "var(--dsw-alias-brand-primary, #0969da)",
    color: "#ffffff",
    fontSize: "13px",
    cursor: "pointer"
  },
  notice: { margin: 0, fontSize: "12px" },
  checkboxRow: { display: "flex", alignItems: "center", gap: "8px" }
};
function Field({ field, draft, disabled, errors, onChange }) {
  const error = errors.find((item) => item.field === field.key);
  const id = `coderag-setting-${field.key}`;
  const common = {
    id,
    style: styles.control,
    disabled,
    "aria-invalid": error !== void 0
  };
  if (field.kind === "boolean") {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.field, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.checkboxRow, children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "input",
          {
            id,
            type: "checkbox",
            checked: draft[field.key] === true,
            disabled,
            onChange: (event) => onChange(field.key, event.target.checked)
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { htmlFor: id, children: field.label })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: field.hint }),
      error === void 0 ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.error, role: "alert", children: error.message })
    ] });
  }
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.field, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { style: styles.labelRow, htmlFor: id, children: field.label }),
    field.kind === "select" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("select", { ...common, value: String(draft[field.key] ?? ""), onChange: (event) => onChange(field.key, event.target.value), children: field.options.map((option) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: option.value, children: option.label }, option.value)) }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
      "input",
      {
        ...common,
        type: "text",
        inputMode: field.kind === "integer" ? "numeric" : void 0,
        placeholder: field.placeholder,
        value: String(draft[field.key] ?? ""),
        onChange: (event) => onChange(field.key, event.target.value)
      }
    ),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: field.hint }),
    error === void 0 ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.error, role: "alert", children: error.message })
  ] });
}
function SettingsPage({ form }) {
  const state = form?.state;
  const acceptedDraft = useMemo(() => toDraft(state?.value ?? DEFAULT_VALUES), [state?.value]);
  const baseDraft = useMemo(() => toDraft(state?.base ?? DEFAULT_VALUES), [state?.base]);
  const [draft, setDraft] = useState(acceptedDraft);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  const [showErrors, setShowErrors] = useState(false);
  const dirtyRef = useRef(false);
  const acceptNextEcho = useRef(false);
  const noticeTimer = useRef(void 0);
  dirtyRef.current = draftKey(draft) !== draftKey(acceptedDraft);
  useEffect(() => {
    if (acceptNextEcho.current || !dirtyRef.current) {
      acceptNextEcho.current = false;
      setDraft(acceptedDraft);
    }
  }, [acceptedDraft]);
  useEffect(() => () => {
    clearTimeout(noticeTimer.current);
  }, []);
  const showNotice = useCallback((next) => {
    setNotice(next);
    clearTimeout(noticeTimer.current);
    if (next?.kind === "saved") {
      noticeTimer.current = setTimeout(() => setNotice(null), SAVED_NOTICE_MS);
    }
  }, []);
  const onChange = useCallback((key, value) => {
    setDraft((previous) => ({ ...previous, [key]: value }));
    setShowErrors(false);
  }, []);
  const errors = useMemo(() => validateValues(draft), [draft]);
  const errorList = showErrors || dirtyRef.current ? errors : [];
  const status = state?.status ?? "loading";
  const writable = state?.writable !== false;
  const disabled = !writable || saving || status !== "ready";
  const dirty = draftKey(draft) !== draftKey(acceptedDraft);
  const onSave = useCallback(async () => {
    if (form === void 0) return;
    setShowErrors(true);
    const validation = validateValues(draft);
    if (validation.length > 0) return;
    setSaving(true);
    setNotice(null);
    try {
      const acceptedByHost = await form.mutate(buildSetOps(draft), state?.revision);
      if (acceptedByHost) {
        acceptNextEcho.current = true;
        showNotice({ kind: "saved" });
      } else {
        showNotice({ kind: "failed", message: "宿主拒绝了这次修改：请检查取值，或配置已被其它地方改写。" });
      }
    } catch (error) {
      showNotice({ kind: "failed", message: `保存失败：${error instanceof Error ? error.message : String(error)}` });
    } finally {
      setSaving(false);
    }
  }, [draft, form, showNotice, state?.revision]);
  const onReset = useCallback(() => {
    setDraft(baseDraft);
    setShowErrors(false);
    showNotice({ kind: "reset" });
  }, [baseDraft, showNotice]);
  if (status === "loading") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: "正在读取 CodeRAG 设置…" });
  if (status === "unavailable") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: "当前 profile 未提供 CodeRAG 设置（coderag 行未激活）。" });
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.root, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.header, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { style: styles.title, children: "CodeRAG 参数设置" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.description, children: "保存后同步到 mcp-coderag 行；也可在 设置 → CodeRAG、Plugins → dsh-coderag，或该行的“配置”里打开。" })
    ] }),
    writable ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.notice, children: "当前 profile 是只读的，不能保存设置。" }),
    GROUPS.map((group) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("fieldset", { style: styles.group, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("legend", { style: styles.legend, children: group.title }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.description, children: group.description }),
      FIELDS.filter((field) => field.group === group.id).map((field) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        Field,
        {
          field,
          draft,
          disabled,
          errors: errorList,
          onChange
        },
        field.key
      ))
    ] }, group.id)),
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.actions, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.primary, disabled, onClick: onSave, children: saving ? "保存中…" : "保存" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.button, disabled, onClick: onReset, children: "恢复默认" }),
      dirty ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.hint, children: "有未保存的修改" }) : null,
      notice?.kind === "saved" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.hint, role: "status", children: "已保存，MCP 已按新环境热重载" }) : null,
      notice?.kind === "reset" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.hint, role: "status", children: "已恢复默认值，点击保存生效。" }) : null,
      notice?.kind === "failed" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.error, role: "alert", children: notice.message }) : null
    ] }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: "保存会写入当前 profile 的 cordis.patch.yml，并把纳管的 CODERAG_* 环境变量同步到 mcp-coderag 行； 只有 CODERAG_SEMANTIC_API_KEY 不在此页出现（请按 README 走环境变量或本机 profile）。" })
  ] });
}
function SettingsSummary() {
  return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "CodeRAG：索引工作区、文件上限、扩展名与可选语义检索；打开配置后保存即可同步到 MCP 行。" });
}
function ConfigFormPage({ configForms }) {
  const form = useMemo(() => configForms.get("coderag"), [configForms]);
  const subscribe = useCallback((listener) => form.subscribe(listener), [form]);
  const getSnapshot = useCallback(() => form.getSnapshot(), [form]);
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const mutate = useCallback((ops, revision) => form.mutate(ops, revision), [form]);
  const pageForm = useMemo(() => ({ state: snapshot, mutate }), [snapshot, mutate]);
  return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsPage, { form: pageForm });
}
function apply(ctx) {
  const configForms = ctx.configForms ?? ctx.get("configForms");
  ctx.slots.inject("settings.section", () => ctx.slots.register(
    {
      name: "settings.section",
      id: "coderag",
      order: 30,
      label: () => "CodeRAG"
    },
    () => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ConfigFormPage, { configForms })
  ));
  ctx.slots.inject("plugins.row.config", () => ctx.slots.register(
    { name: "plugins.row.config", key: ROW_CONFIG_KEY },
    (props) => props?.view === "summary" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsSummary, {}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsPage, { form: props?.form })
  ));
  ctx.slots.inject("plugins.bundle.config", () => ctx.slots.register(
    { name: "plugins.bundle.config", key: BUNDLE_NAME },
    (props) => props?.view === "summary" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsSummary, {}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ConfigFormPage, { configForms })
  ));
}
return module.exports; } });
