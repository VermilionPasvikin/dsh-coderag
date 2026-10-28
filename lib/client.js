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
var React2 = __toESM(require("react"), 1);

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
    const text2 = typeof raw === "string" ? raw.trim() : String(raw);
    if (text2 === "") continue;
    if (!/^(0|[1-9][0-9]*)$/.test(text2)) reject(key, "需要 0 或正整数（0 = 引擎默认）。");
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

// src/plugin/client/admin-panels.jsx
var React = __toESM(require("react"), 1);

// src/plugin/shared/admin-protocol.js
var SEMANTIC_KEY_REF = "CODERAG_SEMANTIC_API_KEY";
var ADMIN_STATE_PATH = "/coderag-admin/state";
var ADMIN_ACTION_PATH = "/coderag-admin/action";
var ADMIN_JOB_PATH = "/coderag-admin/job";
var ADMIN_ACTIONS = Object.freeze(["health", "start-local", "vectorize", "stop", "refresh"]);
var HEALTH_BACKENDS = Object.freeze(["ollama", "openai"]);
var JOB_STATES = Object.freeze(["idle", "running", "stopping", "stopped", "done", "error"]);
function emptyJob() {
  return {
    status: "idle",
    total: null,
    embedded: 0,
    pending: null,
    model: null,
    generatedAt: null,
    startedAt: null,
    finishedAt: null,
    error: null
  };
}
function count(value, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.floor(value) : fallback;
}
function text(value) {
  return typeof value === "string" && value.length > 0 ? value : null;
}
function normalizeAdminStatus(raw) {
  const source = raw !== null && typeof raw === "object" ? raw : {};
  const config = source.config !== null && typeof source.config === "object" ? source.config : {};
  return {
    index_exists: source.index_exists === true,
    vector_exists: source.vector_exists === true,
    model: text(source.model),
    dim: typeof source.dim === "number" && Number.isFinite(source.dim) ? Math.floor(source.dim) : null,
    total_chunks: count(source.total_chunks),
    vectorized_chunks: count(source.vectorized_chunks),
    pending_chunks: count(source.pending_chunks),
    stale_chunks: count(source.stale_chunks),
    generated_at: text(source.generated_at),
    checkpoint_vectors: count(source.checkpoint_vectors),
    config: {
      enabled: config.enabled === true,
      backend: text(config.backend) ?? "",
      url: text(config.url) ?? "",
      model: text(config.model) ?? "",
      allow_remote: config.allow_remote === true,
      key_present: config.key_present === true
    }
  };
}

// src/plugin/shared/admin-client.js
async function adminRequest(path, init = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...init
  });
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`运维接口返回了非 JSON 响应（HTTP ${String(response.status)}）`);
  }
  if (response.ok && body?.ok === true) return body.value;
  const message = typeof body?.error?.message === "string" ? body.error.message : `运维接口失败（HTTP ${String(response.status)}）`;
  throw new Error(message);
}
function fetchAdminState() {
  return adminRequest(ADMIN_STATE_PATH);
}
function fetchAdminJob() {
  return adminRequest(ADMIN_JOB_PATH);
}
function runAdminAction(action, extra = {}) {
  return adminRequest(ADMIN_ACTION_PATH, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action, ...extra })
  });
}
function normalizeJob(raw) {
  const source = raw !== null && typeof raw === "object" ? raw : {};
  const base = emptyJob();
  const numeric = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.floor(value) : null;
  return {
    ...base,
    status: typeof source.status === "string" ? source.status : base.status,
    total: numeric(source.total),
    embedded: numeric(source.embedded) ?? 0,
    pending: numeric(source.pending),
    model: typeof source.model === "string" ? source.model : null,
    generatedAt: typeof source.generatedAt === "string" ? source.generatedAt : null,
    startedAt: numeric(source.startedAt),
    finishedAt: numeric(source.finishedAt),
    error: source.error !== null && typeof source.error === "object" && typeof source.error.message === "string" ? { code: String(source.error.code ?? "unknown"), message: source.error.message } : null
  };
}
function formatCount(value) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("en-US") : "—";
}
function jobLabel(status) {
  switch (status) {
    case "running":
      return "向量化进行中";
    case "stopping":
      return "正在停止…";
    case "stopped":
      return "已停止（检查点保留）";
    case "done":
      return "向量化完成";
    case "error":
      return "向量化失败";
    default:
      return "空闲";
  }
}
function jobPercent(job) {
  const total = job.total;
  if (typeof total !== "number" || total <= 0) return null;
  const done = total - (typeof job.pending === "number" ? job.pending : Math.max(0, total - job.embedded));
  return Math.max(0, Math.min(100, Math.round(done / total * 100)));
}
function jobActive(job) {
  return job.status === "running" || job.status === "stopping";
}
function formatGeneratedAt(value) {
  if (typeof value !== "string" || value === "") return "—";
  return value.replace("T", " ").replace(/\.\d+Z?$/, "").replace(/Z$/, "");
}

// src/plugin/client/admin-panels.jsx
var import_jsx_runtime = require("react/jsx-runtime");
var { useCallback, useEffect, useRef, useState } = React;
var styles = {
  section: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    borderTop: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    paddingTop: "16px",
    marginTop: "4px"
  },
  heading: { margin: 0, fontSize: "15px", fontWeight: 600 },
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    borderRadius: "8px",
    padding: "12px 14px"
  },
  cardTitle: { margin: 0, fontSize: "13px", fontWeight: 600 },
  row: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" },
  column: { display: "flex", flexDirection: "column", gap: "4px" },
  hint: { margin: 0, fontSize: "12px", opacity: 0.72 },
  status: { margin: 0, fontSize: "12px" },
  ok: { color: "var(--dsw-alias-state-success-primary, #1a7f37)" },
  bad: { color: "var(--dsw-alias-state-error-primary, #cf222e)" },
  input: {
    boxSizing: "border-box",
    flex: "1 1 220px",
    minWidth: "160px",
    padding: "6px 8px",
    borderRadius: "6px",
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    background: "var(--dsw-alias-bg-base, #ffffff)",
    color: "var(--dsw-alias-label-primary, #1f2328)",
    fontSize: "13px"
  },
  button: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    background: "var(--dsw-alias-bg-layer-2, transparent)",
    color: "var(--dsw-alias-label-primary, #1f2328)",
    fontSize: "13px",
    cursor: "pointer"
  },
  primary: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid transparent",
    background: "var(--dsw-alias-button-primary-fill, #0969da)",
    color: "var(--dsw-alias-label-primary-inverted, #ffffff)",
    fontSize: "13px",
    cursor: "pointer"
  },
  danger: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid transparent",
    background: "var(--dsw-alias-state-error-primary, #cf222e)",
    color: "#ffffff",
    fontSize: "13px",
    cursor: "pointer"
  },
  bar: {
    height: "6px",
    borderRadius: "999px",
    background: "var(--dsw-alias-bg-layer-2, #f0f0f0)",
    overflow: "hidden"
  },
  barFill: {
    height: "100%",
    background: "var(--dsw-alias-button-primary-fill, #0969da)",
    transition: "width .3s ease"
  },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "6px 16px" },
  stat: { margin: 0, fontSize: "12px" },
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgb(0 0 0 / 45%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1e3
  },
  dialog: {
    maxWidth: "520px",
    width: "calc(100% - 48px)",
    background: "var(--dsw-alias-bg-layer-2, #ffffff)",
    color: "var(--dsw-alias-label-primary, #1f2328)",
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    borderRadius: "10px",
    padding: "16px 18px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    boxShadow: "0 16px 48px rgb(0 0 0 / 28%)"
  },
  dialogTitle: { margin: 0, fontSize: "14px", fontWeight: 600 },
  dialogBody: { margin: 0, fontSize: "13px", whiteSpace: "pre-wrap", wordBreak: "break-word" }
};
function ErrorDialog({ error, onClose }) {
  if (error === null) return null;
  return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: styles.overlay, role: "presentation", onClick: (event) => {
    if (event.target === event.currentTarget) onClose();
  }, children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.dialog, role: "dialog", "aria-modal": "true", "aria-label": "CodeRAG 运维错误", children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h4", { style: styles.dialogTitle, children: "操作失败" }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.dialogBody, children: error }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: styles.row, children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.primary, onClick: onClose, children: "关闭" }) })
  ] }) });
}
function Panel({ title, description, children }) {
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", { style: styles.card, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h4", { style: styles.cardTitle, children: title }),
    description === void 0 ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: description }),
    children
  ] });
}
function CredentialPanel({ remote }) {
  const [status, setStatus] = useState({ phase: "loading" });
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    if (remote?.credentials === void 0) {
      setStatus({ phase: "unavailable" });
      return;
    }
    setStatus({ phase: "loading" });
    let response;
    try {
      response = await remote.credentials.describe([SEMANTIC_KEY_REF]);
    } catch (failure) {
      setStatus({ phase: "error", message: failure instanceof Error ? failure.message : String(failure) });
      return;
    }
    if (!response?.ok) {
      setStatus({ phase: "error", message: response?.error?.message ?? "读取凭据状态失败" });
      return;
    }
    const info = response.value?.[SEMANTIC_KEY_REF];
    setStatus({
      phase: "ready",
      configured: info?.configured === true,
      writable: info?.writable !== false,
      source: typeof info?.source === "string" ? info.source : null
    });
  }, [remote]);
  useEffect(() => {
    void load();
  }, [load]);
  const refreshHostEnv = useCallback(async () => {
    try {
      await runAdminAction("refresh");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);
  const save = useCallback(async () => {
    if (remote?.credentials === void 0 || draft.trim() === "" || busy) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await remote.credentials.set(SEMANTIC_KEY_REF, draft);
      if (!response?.ok) {
        setError(response?.error?.message ?? "保存 API Key 失败");
        return;
      }
      setDraft("");
      setNotice("已配置，不可查看。");
      await load();
      setBusy(false);
      await refreshHostEnv();
      setNotice("已配置，不可查看。Host 已把新 key 同步到 mcp-coderag 行。");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [busy, draft, load, refreshHostEnv, remote]);
  const remove = useCallback(async () => {
    if (remote?.credentials === void 0 || busy) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await remote.credentials.unset(SEMANTIC_KEY_REF);
      if (!response?.ok) {
        setError(response?.error?.message ?? "删除 API Key 失败");
        return;
      }
      setConfirming(false);
      setNotice("已删除云端 API Key。");
      await load();
      setBusy(false);
      await refreshHostEnv();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [busy, load, refreshHostEnv, remote]);
  const unavailable = status.phase === "unavailable";
  const configured = status.phase === "ready" && status.configured === true;
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
    Panel,
    {
      title: "云端 API Key",
      description: "只写入 DSH credentials 服务，不写 profile patch、不回读、不显示。Host 在同步 MCP 行与运维子进程时用它。",
      children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.status, children: [
          "状态：",
          status.phase === "loading" ? "读取中…" : unavailable ? "当前 profile 没有 credentials 服务" : configured ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { style: styles.ok, children: [
            "已配置（不可查看）",
            status.source === void 0 ? "" : `，来源 ${status.source}`
          ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.bad, children: "未配置" })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.row, children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "input",
            {
              style: styles.input,
              type: "password",
              autoComplete: "new-password",
              placeholder: configured ? "输入新 key 以轮换" : "粘贴云端 embedding API key",
              value: draft,
              disabled: busy || unavailable,
              onChange: (event) => setDraft(event.target.value)
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.primary, disabled: busy || unavailable || draft.trim() === "", onClick: save, children: busy ? "保存中…" : "保存" }),
          configured ? confirming ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { style: styles.row, children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.hint, children: "确认删除已配置的 key？" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.danger, disabled: busy, onClick: remove, children: "确认删除" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.button, disabled: busy, onClick: () => setConfirming(false), children: "取消" })
          ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.button, disabled: busy, onClick: () => setConfirming(true), children: "删除" }) : null
        ] }),
        notice === null ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { ...styles.status, ...styles.ok }, role: "status", children: notice }),
        status.phase === "error" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { ...styles.status, ...styles.bad }, children: status.message }) : null,
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorDialog, { error, onClose: () => setError(null) })
      ]
    }
  );
}
function BackendPanel({ values }) {
  const [busy, setBusy] = useState(null);
  const [health, setHealth] = useState({});
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const check = useCallback(async (backend) => {
    if (busy !== null) return;
    setBusy(backend);
    setNotice(null);
    try {
      const value = await runAdminAction("health", { backend });
      setHealth((previous) => ({ ...previous, [backend]: value }));
      if (value?.ok !== true) setError(value?.detail || `${backend} 后端不可用`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  }, [busy]);
  const startLocal = useCallback(async () => {
    if (busy !== null) return;
    setBusy("start-local");
    setNotice(null);
    try {
      const value = await runAdminAction("start-local");
      setNotice(`本地后端已就绪：${value?.url ?? ""}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  }, [busy]);
  const backendLine = (backend) => {
    const result = health[backend];
    if (result === void 0) return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.status, children: [
      backend === "ollama" ? "本地 ollama" : "云端 openai",
      "：未检查"
    ] });
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.status, children: [
      backend === "ollama" ? "本地 ollama" : "云端 openai",
      "：",
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: result.ok ? styles.ok : styles.bad, children: result.ok ? " 连通" : " 不可用" }),
      result.url === void 0 || result.url === "" ? "" : ` · ${result.url}`,
      result.model === void 0 || result.model === "" ? "" : ` · 模型 ${result.model_present ? `${result.model}（已就绪）` : `${result.model}（缺失）`}`,
      result.detail === void 0 || result.detail === "" ? "" : ` · ${result.detail}`
    ] });
  };
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
    Panel,
    {
      title: "语义后端",
      description: `当前保存值：后端 ${values?.semanticBackend || "默认 ollama"} · URL ${values?.semanticUrl || "默认"} · 模型 ${values?.semanticModel || "默认"}。检查使用已保存的配置。`,
      children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.row, children: [
          HEALTH_BACKENDS.map((backend) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              style: styles.button,
              disabled: busy !== null,
              onClick: () => {
                void check(backend);
              },
              children: busy === backend ? "检查中…" : backend === "ollama" ? "检查本地连通性" : "检查云端连通性"
            },
            backend
          )),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.button, disabled: busy !== null, onClick: () => {
            void startLocal();
          }, children: busy === "start-local" ? "启动中…" : "一键启动本地后端" })
        ] }),
        backendLine("ollama"),
        backendLine("openai"),
        notice === null ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { ...styles.status, ...styles.ok }, role: "status", children: notice }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorDialog, { error, onClose: () => setError(null) })
      ]
    }
  );
}
function VectorPanel({ dirty }) {
  const [state, setState] = useState({ phase: "loading" });
  const [job, setJob] = useState(normalizeJob(void 0));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const previousStatus = useRef(job.status);
  const refresh = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      const raw = await fetchAdminState();
      setState({ phase: "ready", value: normalizeAdminStatus(raw) });
    } catch (failure) {
      setState({ phase: "error", message: failure instanceof Error ? failure.message : String(failure) });
    }
  }, []);
  const loadJob = useCallback(async () => {
    try {
      const next = normalizeJob(await fetchAdminJob());
      setJob(next);
      return next;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      return void 0;
    }
  }, []);
  useEffect(() => {
    void refresh();
    void loadJob();
  }, [loadJob, refresh]);
  useEffect(() => {
    if (!jobActive(job)) return;
    const timer = setInterval(() => {
      void (async () => {
        const next = await loadJob();
        if (next !== void 0 && !jobActive(next)) await refresh();
      })();
    }, 1e3);
    return () => clearInterval(timer);
  }, [job, loadJob, refresh]);
  useEffect(() => {
    if (previousStatus.current !== "done" && job.status === "done") void refresh();
    previousStatus.current = job.status;
  }, [job.status, refresh]);
  const act = useCallback(async (action) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const value2 = await runAdminAction(action);
      if (action === "stop") setJob(normalizeJob(value2));
      else if (action === "vectorize") setJob(normalizeJob(value2));
      else await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [busy, refresh]);
  const value = state.phase === "ready" ? state.value : void 0;
  const running = jobActive(job);
  const percent = jobPercent(job);
  const actionDisabled = dirty || busy;
  const primaryLabel = running ? null : value?.vector_exists === true && value?.pending_chunks > 0 ? "向量化增量" : "开始向量化";
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
    Panel,
    {
      title: "向量数据库",
      description: "使用已保存的工作区根；索引与检查点都在 <root>/.coderag/ 下，停止不会删除检查点。",
      children: [
        dirty ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { ...styles.status, ...styles.bad }, children: "有未保存的设置改动，请先保存再操作向量库（避免用旧根跑任务）。" }) : null,
        state.phase === "loading" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: styles.hint, children: "正在读取向量库状态…" }) : null,
        state.phase === "error" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { ...styles.status, ...styles.bad }, children: state.message }) : null,
        value === void 0 ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.grid, children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "索引：",
            value.index_exists ? "存在" : "不存在"
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "向量库：",
            value.vector_exists ? "存在" : "不存在"
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "模型：",
            value.model ?? "—",
            value.dim === null ? "" : `（${value.dim} 维）`
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "总 chunk：",
            formatCount(value.total_chunks)
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "已向量化：",
            formatCount(value.vectorized_chunks)
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "待向量化：",
            formatCount(value.pending_chunks)
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "过期 chunk：",
            formatCount(value.stale_chunks)
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "检查点：",
            formatCount(value.checkpoint_vectors)
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            "生成时间：",
            formatGeneratedAt(value.generated_at)
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.row, children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.button, disabled: busy, onClick: () => {
            void refresh();
            void loadJob();
          }, children: "刷新" }),
          running ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.danger, disabled: busy, onClick: () => {
            void act("stop");
          }, children: "停止" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", { type: "button", style: styles.primary, disabled: actionDisabled, onClick: () => {
            void act("vectorize");
          }, children: primaryLabel }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { style: styles.hint, children: jobLabel(job.status) })
        ] }),
        running || job.embedded > 0 || job.status === "done" ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.column, children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: styles.bar, children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { ...styles.barFill, width: `${percent ?? 5}%` } }) }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { style: styles.stat, children: [
            formatCount(job.embedded),
            " / ",
            formatCount(job.total),
            " 已处理",
            job.pending === null ? "" : ` · 待处理 ${formatCount(job.pending)}`,
            percent === null ? "" : ` · ${percent}%`
          ] })
        ] }) : null,
        job.error === null ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { ...styles.status, ...styles.bad }, children: job.error.message }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorDialog, { error, onClose: () => setError(null) })
      ]
    }
  );
}
function AdminPanels({ remote, values, dirty }) {
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: styles.section, children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { style: styles.heading, children: "CodeRAG 运维" }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CredentialPanel, { remote }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(BackendPanel, { values }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(VectorPanel, { dirty: dirty === true })
  ] });
}

// src/plugin/client/index.jsx
var import_jsx_runtime2 = require("react/jsx-runtime");
var inject = ["slots", "configForms", "remote", "remote.credentials"];
var { useCallback: useCallback2, useEffect: useEffect2, useMemo, useRef: useRef2, useState: useState2, useSyncExternalStore } = React2;
var SAVED_NOTICE_MS = 4e3;
var styles2 = {
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
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
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
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    background: "var(--dsw-alias-bg-base, #ffffff)",
    color: "var(--dsw-alias-label-primary, #1f2328)",
    fontSize: "13px"
  },
  hint: { margin: 0, fontSize: "12px", opacity: 0.72 },
  error: { margin: 0, fontSize: "12px", color: "var(--dsw-alias-state-error-primary, #cf222e)" },
  actions: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" },
  button: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid var(--dsw-alias-border-l2, #d0d7de)",
    background: "var(--dsw-alias-bg-layer-2, transparent)",
    color: "var(--dsw-alias-label-primary, #1f2328)",
    fontSize: "13px",
    cursor: "pointer"
  },
  primary: {
    padding: "6px 14px",
    borderRadius: "6px",
    border: "1px solid transparent",
    background: "var(--dsw-alias-button-primary-fill, #0969da)",
    color: "var(--dsw-alias-label-primary-inverted, #ffffff)",
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
    style: styles2.control,
    disabled,
    "aria-invalid": error !== void 0
  };
  if (field.kind === "boolean") {
    return /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("div", { style: styles2.field, children: [
      /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("div", { style: styles2.checkboxRow, children: [
        /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(
          "input",
          {
            id,
            type: "checkbox",
            checked: draft[field.key] === true,
            disabled,
            onChange: (event) => onChange(field.key, event.target.checked)
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("label", { htmlFor: id, children: field.label })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.hint, children: field.hint }),
      error === void 0 ? null : /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.error, role: "alert", children: error.message })
    ] });
  }
  return /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("div", { style: styles2.field, children: [
    /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("label", { style: styles2.labelRow, htmlFor: id, children: field.label }),
    field.kind === "select" ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("select", { ...common, value: String(draft[field.key] ?? ""), onChange: (event) => onChange(field.key, event.target.value), children: field.options.map((option) => /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("option", { value: option.value, children: option.label }, option.value)) }) : /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(
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
    /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.hint, children: field.hint }),
    error === void 0 ? null : /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.error, role: "alert", children: error.message })
  ] });
}
function SettingsPage({ form, remote }) {
  const state = form?.state;
  const acceptedDraft = useMemo(() => toDraft(state?.value ?? DEFAULT_VALUES), [state?.value]);
  const baseDraft = useMemo(() => toDraft(state?.base ?? DEFAULT_VALUES), [state?.base]);
  const [draft, setDraft] = useState2(acceptedDraft);
  const [saving, setSaving] = useState2(false);
  const [notice, setNotice] = useState2(null);
  const [showErrors, setShowErrors] = useState2(false);
  const dirtyRef = useRef2(false);
  const acceptNextEcho = useRef2(false);
  const noticeTimer = useRef2(void 0);
  dirtyRef.current = draftKey(draft) !== draftKey(acceptedDraft);
  useEffect2(() => {
    if (acceptNextEcho.current || !dirtyRef.current) {
      acceptNextEcho.current = false;
      setDraft(acceptedDraft);
    }
  }, [acceptedDraft]);
  useEffect2(() => () => {
    clearTimeout(noticeTimer.current);
  }, []);
  const showNotice = useCallback2((next) => {
    setNotice(next);
    clearTimeout(noticeTimer.current);
    if (next?.kind === "saved") {
      noticeTimer.current = setTimeout(() => setNotice(null), SAVED_NOTICE_MS);
    }
  }, []);
  const onChange = useCallback2((key, value) => {
    setDraft((previous) => ({ ...previous, [key]: value }));
    setShowErrors(false);
  }, []);
  const errors = useMemo(() => validateValues(draft), [draft]);
  const errorList = showErrors || dirtyRef.current ? errors : [];
  const status = state?.status ?? "loading";
  const writable = state?.writable !== false;
  const disabled = !writable || saving || status !== "ready";
  const dirty = draftKey(draft) !== draftKey(acceptedDraft);
  const onSave = useCallback2(async () => {
    if (form === void 0) return;
    setShowErrors(true);
    const validation = validateValues(draft);
    if (validation.length > 0) return;
    setSaving(true);
    setNotice(null);
    let timer;
    try {
      const acceptedByHost = await Promise.race([
        form.mutate(buildSetOps(draft), state?.revision),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error("宿主 15 秒未响应")), 15e3);
        })
      ]);
      if (acceptedByHost) {
        acceptNextEcho.current = true;
        showNotice({ kind: "saved" });
      } else {
        showNotice({ kind: "failed", message: "宿主拒绝了这次修改：请检查取值，或配置已被其它地方改写。" });
      }
    } catch (error) {
      showNotice({ kind: "failed", message: `保存失败：${error instanceof Error ? error.message : String(error)}` });
    } finally {
      clearTimeout(timer);
      setSaving(false);
    }
  }, [draft, form, showNotice, state?.revision]);
  const onReset = useCallback2(() => {
    setDraft(baseDraft);
    setShowErrors(false);
    showNotice({ kind: "reset" });
  }, [baseDraft, showNotice]);
  if (status === "loading") return /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.hint, children: "正在读取 CodeRAG 设置…" });
  if (status === "unavailable") return /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.hint, children: "当前 profile 未提供 CodeRAG 设置（coderag 行未激活）。" });
  return /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("div", { style: styles2.root, children: [
    /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("div", { style: styles2.header, children: [
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("h3", { style: styles2.title, children: "CodeRAG 参数设置" }),
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.description, children: "保存后同步到 mcp-coderag 行；也可在 设置 → CodeRAG、Plugins → dsh-coderag，或该行的“配置”里打开。" })
    ] }),
    writable ? null : /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.notice, children: "当前 profile 是只读的，不能保存设置。" }),
    GROUPS.map((group) => /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("fieldset", { style: styles2.group, children: [
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("legend", { style: styles2.legend, children: group.title }),
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.description, children: group.description }),
      FIELDS.filter((field) => field.group === group.id).map((field) => /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(
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
    /* @__PURE__ */ (0, import_jsx_runtime2.jsxs)("div", { style: styles2.actions, children: [
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("button", { type: "button", style: styles2.primary, disabled, onClick: onSave, children: saving ? "保存中…" : "保存" }),
      /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("button", { type: "button", style: styles2.button, disabled, onClick: onReset, children: "恢复默认" }),
      dirty ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("span", { style: styles2.hint, children: "有未保存的修改" }) : null,
      notice?.kind === "saved" ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("span", { style: styles2.hint, role: "status", children: "已保存，MCP 已按新环境热重载" }) : null,
      notice?.kind === "reset" ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("span", { style: styles2.hint, role: "status", children: "已恢复默认值，点击保存生效。" }) : null,
      notice?.kind === "failed" ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("span", { style: styles2.error, role: "alert", children: notice.message }) : null
    ] }),
    /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("p", { style: styles2.hint, children: "保存会写入当前 profile 的 cordis.patch.yml，并把纳管的 CODERAG_* 环境变量同步到 mcp-coderag 行； 云端 API Key 在下面的运维区写入 DSH credentials 服务，不落 profile。" }),
    /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(AdminPanels, { remote, values: state?.value, dirty })
  ] });
}
function SettingsSummary() {
  return /* @__PURE__ */ (0, import_jsx_runtime2.jsx)("span", { children: "CodeRAG：索引工作区、文件上限、扩展名与可选语义检索；打开配置后保存即可同步到 MCP 行。" });
}
function ConfigFormPage({ configForms, remote }) {
  const form = useMemo(() => configForms.get("coderag"), [configForms]);
  const subscribe = useCallback2((listener) => form.subscribe(listener), [form]);
  const getSnapshot = useCallback2(() => form.getSnapshot(), [form]);
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const mutate = useCallback2((ops, revision) => form.mutate(ops, revision), [form]);
  const pageForm = useMemo(() => ({ state: snapshot, mutate }), [snapshot, mutate]);
  return /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(SettingsPage, { form: pageForm, remote });
}
function apply(ctx) {
  const configForms = ctx.configForms ?? ctx.get("configForms");
  const remote = ctx.remote;
  ctx.slots.inject("settings.section", () => ctx.slots.register(
    {
      name: "settings.section",
      id: "coderag",
      order: 30,
      label: () => "CodeRAG"
    },
    () => /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(ConfigFormPage, { configForms, remote })
  ));
  ctx.slots.inject("plugins.row.config", () => ctx.slots.register(
    { name: "plugins.row.config", key: ROW_CONFIG_KEY },
    (props) => props?.view === "summary" ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(SettingsSummary, {}) : /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(SettingsPage, { form: props?.form, remote })
  ));
  ctx.slots.inject("plugins.bundle.config", () => ctx.slots.register(
    { name: "plugins.bundle.config", key: BUNDLE_NAME },
    (props) => props?.view === "summary" ? /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(SettingsSummary, {}) : /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(ConfigFormPage, { configForms, remote })
  ));
}
return module.exports; } });
