// node_modules/@deepseek-ai/cosmokit/lib/index.js
function isNullable(value) {
  return value === null || value === void 0;
}
function isPlainObject(data) {
  return data && typeof data === "object" && !Array.isArray(data);
}
function filterKeys(object, filter) {
  return Object.fromEntries(Object.entries(object).filter(([key, value]) => filter(key, value)));
}
function mapValues(object, transform) {
  return Object.fromEntries(Object.entries(object).map(([key, value]) => [key, transform(value, key)]));
}
function pick(source, keys, forced) {
  if (!keys) return { ...source };
  const result = {};
  for (const key of keys) if (forced || source[key] !== void 0) result[key] = source[key];
  return result;
}
var write = /* @__PURE__ */ Symbol.for("cosmokit.volatile.write");
function snapshot(value, ancestors = /* @__PURE__ */ new Set()) {
  if (typeof value === "function") throw new TypeError("volatile config cannot contain functions");
  if (value === null || typeof value !== "object") return value;
  if (ancestors.has(value)) throw new TypeError("volatile config cannot contain cycles");
  ancestors.add(value);
  try {
    if (Array.isArray(value)) return Object.freeze(value.map((item) => snapshot(item, ancestors)));
    if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) throw new TypeError("volatile config objects must be plain objects or arrays");
    return Object.freeze(Object.fromEntries(Object.entries(value).map(([key, item]) => [key, snapshot(item, ancestors)])));
  } finally {
    ancestors.delete(value);
  }
}
function createVolatile(value) {
  let current = snapshot(value);
  return Object.freeze({
    get: () => current,
    [write]: (value2) => {
      current = value2;
    }
  });
}
function isVolatile(value) {
  return typeof value === "object" && value !== null && write in value;
}
function is(type, value) {
  if (arguments.length === 1) return (value2) => is(type, value2);
  return type in globalThis && value instanceof globalThis[type] || Object.prototype.toString.call(value).slice(8, -1) === type;
}
function isArrayBufferLike(value) {
  return is("ArrayBuffer", value) || is("SharedArrayBuffer", value);
}
function isArrayBufferSource(value) {
  return isArrayBufferLike(value) || ArrayBuffer.isView(value);
}
var Binary;
(function(Binary2) {
  Binary2.is = isArrayBufferLike;
  Binary2.isSource = isArrayBufferSource;
  function fromSource(source) {
    if (ArrayBuffer.isView(source)) return source.buffer.slice(source.byteOffset, source.byteOffset + source.byteLength);
    else return source;
  }
  Binary2.fromSource = fromSource;
  function toBase64(source) {
    source = fromSource(source);
    if (typeof Buffer !== "undefined") return Buffer.from(source).toString("base64");
    let binary = "";
    const bytes = new Uint8Array(source);
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }
  Binary2.toBase64 = toBase64;
  function fromBase64(source) {
    if (typeof Buffer !== "undefined") return fromSource(Buffer.from(source, "base64"));
    return Uint8Array.from(atob(source), (c) => c.charCodeAt(0));
  }
  Binary2.fromBase64 = fromBase64;
  function toHex(source) {
    source = fromSource(source);
    if (typeof Buffer !== "undefined") return Buffer.from(source).toString("hex");
    return Array.from(new Uint8Array(source), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  Binary2.toHex = toHex;
  function fromHex(source) {
    if (typeof Buffer !== "undefined") return fromSource(Buffer.from(source, "hex"));
    const hex = source.length % 2 === 0 ? source : source.slice(0, source.length - 1);
    const buffer = [];
    for (let i = 0; i < hex.length; i += 2) buffer.push(parseInt(`${hex[i]}${hex[i + 1]}`, 16));
    return Uint8Array.from(buffer).buffer;
  }
  Binary2.fromHex = fromHex;
})(Binary || (Binary = {}));
var base64ToArrayBuffer = Binary.fromBase64;
var arrayBufferToBase64 = Binary.toBase64;
var hexToArrayBuffer = Binary.fromHex;
var arrayBufferToHex = Binary.toHex;
function clone(source, refs = /* @__PURE__ */ new Map()) {
  if (!source || typeof source !== "object") return source;
  if (is("Date", source)) return new Date(source.valueOf());
  if (is("RegExp", source)) return new RegExp(source.source, source.flags);
  if (isArrayBufferLike(source)) return source.slice(0);
  if (ArrayBuffer.isView(source)) return source.buffer.slice(source.byteOffset, source.byteOffset + source.byteLength);
  const cached = refs.get(source);
  if (cached) return cached;
  if (Array.isArray(source)) {
    const result2 = [];
    refs.set(source, result2);
    source.forEach((value, index) => {
      result2[index] = Reflect.apply(clone, null, [value, refs]);
    });
    return result2;
  }
  const result = Object.create(Object.getPrototypeOf(source));
  refs.set(source, result);
  for (const key of Reflect.ownKeys(source)) {
    const descriptor = { ...Reflect.getOwnPropertyDescriptor(source, key) };
    if ("value" in descriptor) descriptor.value = Reflect.apply(clone, null, [descriptor.value, refs]);
    Reflect.defineProperty(result, key, descriptor);
  }
  return result;
}
function deepEqual(a, b, strict) {
  const ancestors = /* @__PURE__ */ new Set();
  function compare(a2, b2) {
    if (a2 === b2) return true;
    if (isVolatile(a2) || isVolatile(b2)) return isVolatile(a2) && isVolatile(b2);
    if (!strict && isNullable(a2) && isNullable(b2)) return true;
    if (typeof a2 !== typeof b2 || typeof a2 !== "object" || !a2 || !b2) return false;
    if (ancestors.has(a2)) return false;
    function check(test, then) {
      return test(a2) ? test(b2) ? then(a2, b2) : false : test(b2) ? false : void 0;
    }
    ancestors.add(a2);
    try {
      return check(Array.isArray, (a3, b3) => {
        if (a3.length !== b3.length) return false;
        for (let index = 0; index < a3.length; index++) if (!compare(a3[index], b3[index])) return false;
        return true;
      }) ?? check(is("Date"), (a3, b3) => a3.valueOf() === b3.valueOf()) ?? check(is("URL"), (a3, b3) => a3.href === b3.href) ?? check(is("RegExp"), (a3, b3) => a3.source === b3.source && a3.flags === b3.flags) ?? check(isArrayBufferLike, (a3, b3) => {
        if (a3.byteLength !== b3.byteLength) return false;
        const viewA = new Uint8Array(a3);
        const viewB = new Uint8Array(b3);
        for (let i = 0; i < viewA.length; i++) if (viewA[i] !== viewB[i]) return false;
        return true;
      }) ?? ((!strict || [a2, b2].every((value) => Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)) && Object.keys({
        ...a2,
        ...b2
      }).every((key) => compare(a2[key], b2[key])));
    } finally {
      ancestors.delete(a2);
    }
  }
  return compare(a, b);
}
var Time;
(function(Time2) {
  Time2.millisecond = 1;
  Time2.second = 1e3;
  Time2.minute = Time2.second * 60;
  Time2.hour = Time2.minute * 60;
  Time2.day = Time2.hour * 24;
  Time2.week = Time2.day * 7;
  let timezoneOffset = (/* @__PURE__ */ new Date()).getTimezoneOffset();
  function setTimezoneOffset(offset) {
    timezoneOffset = offset;
  }
  Time2.setTimezoneOffset = setTimezoneOffset;
  function getTimezoneOffset() {
    return timezoneOffset;
  }
  Time2.getTimezoneOffset = getTimezoneOffset;
  function getDateNumber(date2 = /* @__PURE__ */ new Date(), offset) {
    if (typeof date2 === "number") date2 = new Date(date2);
    if (offset === void 0) offset = timezoneOffset;
    return Math.floor((date2.valueOf() / Time2.minute - offset) / 1440);
  }
  Time2.getDateNumber = getDateNumber;
  function fromDateNumber(value, offset) {
    const date2 = new Date(value * Time2.day);
    if (offset === void 0) offset = timezoneOffset;
    return new Date(+date2 + offset * Time2.minute);
  }
  Time2.fromDateNumber = fromDateNumber;
  const numeric = /\d+(?:\.\d+)?/.source;
  const timeRegExp = new RegExp(`^${[
    "w(?:eek(?:s)?)?",
    "d(?:ay(?:s)?)?",
    "h(?:our(?:s)?)?",
    "m(?:in(?:ute)?(?:s)?)?",
    "s(?:ec(?:ond)?(?:s)?)?"
  ].map((unit) => `(${numeric}${unit})?`).join("")}$`);
  function parseTime(source) {
    const capture = timeRegExp.exec(source);
    if (!capture) return 0;
    return (parseFloat(capture[1]) * Time2.week || 0) + (parseFloat(capture[2]) * Time2.day || 0) + (parseFloat(capture[3]) * Time2.hour || 0) + (parseFloat(capture[4]) * Time2.minute || 0) + (parseFloat(capture[5]) * Time2.second || 0);
  }
  Time2.parseTime = parseTime;
  function parseDate(date2) {
    const parsed = parseTime(date2);
    if (parsed) date2 = Date.now() + parsed;
    else if (/^\d{1,2}(:\d{1,2}){1,2}$/.test(date2)) date2 = `${(/* @__PURE__ */ new Date()).toLocaleDateString()}-${date2}`;
    else if (/^\d{1,2}-\d{1,2}-\d{1,2}(:\d{1,2}){1,2}$/.test(date2)) date2 = `${(/* @__PURE__ */ new Date()).getFullYear()}-${date2}`;
    return date2 ? new Date(date2) : /* @__PURE__ */ new Date();
  }
  Time2.parseDate = parseDate;
  function format(ms) {
    const abs = Math.abs(ms);
    if (abs >= Time2.day - Time2.hour / 2) return Math.round(ms / Time2.day) + "d";
    else if (abs >= Time2.hour - Time2.minute / 2) return Math.round(ms / Time2.hour) + "h";
    else if (abs >= Time2.minute - Time2.second / 2) return Math.round(ms / Time2.minute) + "m";
    else if (abs >= Time2.second) return Math.round(ms / Time2.second) + "s";
    return ms + "ms";
  }
  Time2.format = format;
  function toDigits(source, length = 2) {
    return source.toString().padStart(length, "0");
  }
  Time2.toDigits = toDigits;
  function template(template2, time = /* @__PURE__ */ new Date()) {
    return template2.replace("yyyy", time.getFullYear().toString()).replace("yy", time.getFullYear().toString().slice(2)).replace("MM", toDigits(time.getMonth() + 1)).replace("dd", toDigits(time.getDate())).replace("hh", toDigits(time.getHours())).replace("mm", toDigits(time.getMinutes())).replace("ss", toDigits(time.getSeconds())).replace("SSS", toDigits(time.getMilliseconds(), 3));
  }
  Time2.template = template;
})(Time || (Time = {}));

// node_modules/@deepseek-ai/schemastery/lib/index.mjs
var kSchema = /* @__PURE__ */ Symbol.for("schemastery");
var kValidationError = /* @__PURE__ */ Symbol.for("ValidationError");
globalThis.__schemastery_index__ ??= 0;
globalThis.__schemastery_refs__ = void 0;
var ValidationError = class extends TypeError {
  options;
  name = "ValidationError";
  constructor(message, options) {
    let prefix = "$";
    for (const segment of options.path || []) if (typeof segment === "string") prefix += "." + segment;
    else if (typeof segment === "number") prefix += "[" + segment + "]";
    else if (typeof segment === "symbol") prefix += `[Symbol(${segment.toString()})]`;
    if (prefix.startsWith(".")) prefix = prefix.slice(1);
    super((prefix === "$" ? "" : `${prefix} `) + message);
    this.options = options;
  }
  static is(error) {
    return !!error?.[kValidationError];
  }
};
Object.defineProperty(ValidationError.prototype, kValidationError, { value: true });
var Schema = function(options) {
  const schema = function(data, options2 = {}) {
    return Schema.resolve(data, schema, options2)[0];
  };
  if (options.refs) {
    const refs = mapValues(options.refs, (options2) => new Schema(options2));
    const getRef = (uid) => refs[uid];
    for (const key in refs) {
      const options2 = refs[key];
      options2.sKey = getRef(options2.sKey);
      options2.inner = getRef(options2.inner);
      options2.list = options2.list && options2.list.map(getRef);
      options2.dict = options2.dict && mapValues(options2.dict, getRef);
    }
    return refs[options.uid];
  }
  Object.assign(schema, options);
  if (typeof schema.callback === "string") try {
    schema.callback = new Function("return " + schema.callback)();
  } catch {
  }
  Object.defineProperty(schema, "uid", { value: globalThis.__schemastery_index__++ });
  Object.setPrototypeOf(schema, Schema.prototype);
  schema.meta ||= {};
  schema.toString = schema.toString.bind(schema);
  return schema;
};
Schema.prototype = Object.create(Function.prototype);
Schema.prototype[kSchema] = true;
Object.defineProperty(Schema.prototype, "~standard", { get() {
  return {
    version: 1,
    vendor: "schemastery",
    validate: (value) => {
      try {
        return { value: Schema.resolve(value, this, {})[0] };
      } catch (error) {
        if (ValidationError.is(error)) return { issues: [{
          message: error.message,
          path: error.options.path
        }] };
        throw error;
      }
    }
  };
} });
Schema.ValidationError = ValidationError;
Schema.prototype.toJSON = function toJSON() {
  if (globalThis.__schemastery_refs__) {
    globalThis.__schemastery_refs__[this.uid] ??= JSON.parse(JSON.stringify({ ...this }));
    return this.uid;
  }
  globalThis.__schemastery_refs__ = { [this.uid]: { ...this } };
  globalThis.__schemastery_refs__[this.uid] = JSON.parse(JSON.stringify({ ...this }));
  const result = {
    uid: this.uid,
    refs: globalThis.__schemastery_refs__
  };
  globalThis.__schemastery_refs__ = void 0;
  return result;
};
Schema.prototype.set = function set(key, value) {
  this.dict[key] = value;
  return this;
};
Schema.prototype.push = function push(value) {
  this.list.push(value);
  return this;
};
function mergeDesc(original, messages) {
  const result = typeof original === "string" ? { "": original } : { ...original };
  for (const locale in messages) {
    const value = messages[locale];
    if (value?.$description || value?.$desc) result[locale] = value.$description || value.$desc;
    else if (typeof value === "string") result[locale] = value;
  }
  return result;
}
function getInner(value) {
  return value?.$value ?? value?.$inner;
}
function extractKeys(data) {
  return filterKeys(data ?? {}, (key) => !key.startsWith("$"));
}
Schema.prototype.i18n = function i18n(messages) {
  const schema = Schema(this);
  const desc = mergeDesc(schema.meta.description, messages);
  if (Object.keys(desc).length) schema.meta.description = desc;
  if (schema.dict) schema.dict = mapValues(schema.dict, (inner, key) => {
    return inner.i18n(mapValues(messages, (data) => getInner(data)?.[key] ?? data?.[key]));
  });
  if (schema.list) schema.list = schema.list.map((inner, index) => {
    return inner.i18n(mapValues(messages, (data = {}) => {
      if (Array.isArray(getInner(data))) return getInner(data)[index];
      if (Array.isArray(data)) return data[index];
      return extractKeys(data);
    }));
  });
  if (schema.inner) schema.inner = schema.inner.i18n(mapValues(messages, (data) => {
    if (getInner(data)) return getInner(data);
    return extractKeys(data);
  }));
  if (schema.sKey) schema.sKey = schema.sKey.i18n(mapValues(messages, (data) => data?.$key));
  return schema;
};
Schema.prototype.extra = function extra(key, value) {
  const schema = Schema(this);
  schema.meta = {
    ...schema.meta,
    [key]: value
  };
  return schema;
};
for (const key of [
  "required",
  "disabled",
  "collapse",
  "hidden",
  "loose"
]) Object.assign(Schema.prototype, { [key](value = true) {
  const schema = Schema(this);
  schema.meta = {
    ...schema.meta,
    [key]: value
  };
  return schema;
} });
Schema.prototype.deprecated = function deprecated() {
  const schema = Schema(this);
  schema.meta.badges ||= [];
  schema.meta.badges.push({
    text: "deprecated",
    type: "danger"
  });
  return schema;
};
Schema.prototype.experimental = function experimental() {
  const schema = Schema(this);
  schema.meta.badges ||= [];
  schema.meta.badges.push({
    text: "experimental",
    type: "warning"
  });
  return schema;
};
Schema.prototype.pattern = function pattern(regexp) {
  const schema = Schema(this);
  const pattern2 = pick(regexp, ["source", "flags"]);
  schema.meta = {
    ...schema.meta,
    pattern: pattern2
  };
  return schema;
};
Schema.prototype.simplify = function simplify(value) {
  if (isVolatile(value)) value = value.get();
  if (deepEqual(value, this.meta.default, this.type === "dict")) return null;
  if (isNullable(value)) return value;
  if (this.type === "object" || this.type === "dict") {
    const result = {};
    for (const key in value) {
      const item = (this.type === "object" ? this.dict[key] : this.inner)?.simplify(value[key]);
      if (this.type === "dict" || !isNullable(item)) result[key] = item;
    }
    if (deepEqual(result, this.meta.default, this.type === "dict")) return null;
    return result;
  } else if (this.type === "array" || this.type === "tuple") {
    const result = [];
    value.forEach((value2, index) => {
      const schema = this.type === "array" ? this.inner : this.list[index];
      const item = schema ? schema.simplify(value2) : value2;
      result.push(item);
    });
    return result;
  } else if (this.type === "intersect") {
    const result = {};
    for (const item of this.list) Object.assign(result, item.simplify(value));
    return result;
  } else if (this.type === "union") for (const schema of this.list) try {
    Schema.resolve(value, schema, {});
    return schema.simplify(value);
  } catch {
  }
  return value;
};
Schema.prototype.toString = function toString(inline) {
  return formatters[this.type]?.(this, inline) ?? `Schema<${this.type}>`;
};
Schema.prototype.role = function role(role, extra2) {
  const schema = Schema(this);
  schema.meta = {
    ...schema.meta,
    role,
    extra: extra2
  };
  return schema;
};
for (const key of [
  "default",
  "link",
  "comment",
  "description",
  "max",
  "min",
  "step"
]) Object.assign(Schema.prototype, { [key](value) {
  const schema = Schema(this);
  schema.meta = {
    ...schema.meta,
    [key]: value
  };
  return schema;
} });
Schema.prototype.volatile = function volatile() {
  if (this.meta.volatile) throw new TypeError("volatile schema is already wrapped");
  return this.extra("volatile", true);
};
var resolvers = {};
var checkedVolatile = /* @__PURE__ */ Symbol("checked-volatile-schema");
function validateVolatileSchema(schema, path = [], blocked = false, seen = /* @__PURE__ */ new Map()) {
  const states = seen.get(schema) ?? /* @__PURE__ */ new Set();
  if (states.has(blocked)) return;
  states.add(blocked);
  seen.set(schema, states);
  if (schema.meta?.volatile && blocked) throw new ValidationError("volatile fields require a fixed object path without an enclosing volatile field", { path });
  const nested = blocked || !!schema.meta?.volatile;
  if (schema.dict) for (const [key, child] of Object.entries(schema.dict)) validateVolatileSchema(child, [...path, key], nested, seen);
  if (schema.sKey) validateVolatileSchema(schema.sKey, [...path, "<key>"], true, seen);
  if (schema.inner && (schema.type !== "lazy" || schema.inner[kSchema])) validateVolatileSchema(schema.inner, [...path, "*"], true, seen);
  if (schema.list) for (let index = 0; index < schema.list.length; index++) validateVolatileSchema(schema.list[index], [...path, String(index)], true, seen);
}
Schema.extend = function extend(type, resolve2) {
  resolvers[type] = resolve2;
};
Schema.resolve = function resolve(data, schema, options = {}, strict = false) {
  if (!schema) return [data];
  if (!options[checkedVolatile]) {
    validateVolatileSchema(schema, options.path);
    options = {
      ...options,
      [checkedVolatile]: true
    };
  }
  if (schema.meta?.volatile) {
    const inner = Schema(schema);
    inner.meta = {
      ...schema.meta,
      volatile: false
    };
    const [value, adapted] = Schema.resolve(data, inner, options, strict);
    try {
      return [createVolatile(value), adapted];
    } catch (error) {
      throw new ValidationError(error instanceof Error ? error.message : String(error), options);
    }
  }
  if (options.ignore?.(data, schema)) return [data];
  if (isNullable(data) && schema.type !== "lazy") {
    if (schema.meta.required) throw new ValidationError(`missing required value`, options);
    let current = schema;
    let fallback = schema.meta.default;
    while (current?.type === "intersect" && isNullable(fallback)) {
      current = current.list[0];
      fallback = current?.meta.default;
    }
    if (isNullable(fallback)) return [data];
    data = clone(fallback);
  }
  const callback = resolvers[schema.type];
  if (!callback) throw new ValidationError(`unsupported type "${schema.type}"`, options);
  try {
    return callback(data, schema, options, strict);
  } catch (error) {
    if (!schema.meta.loose) throw error;
    return [schema.meta.default];
  }
};
Schema.from = function from(source) {
  if (isNullable(source)) return Schema.any();
  else if ([
    "string",
    "number",
    "boolean"
  ].includes(typeof source)) return Schema.const(source).required();
  else if (source[kSchema]) return source;
  else if (typeof source === "function") switch (source) {
    case String:
      return Schema.string().required();
    case Number:
      return Schema.number().required();
    case Boolean:
      return Schema.boolean().required();
    case Function:
      return Schema.function().required();
    default:
      return Schema.is(source).required();
  }
  else throw new TypeError(`cannot infer schema from ${source}`);
};
Schema.lazy = function lazy(builder) {
  const toJSON2 = () => {
    if (!schema.inner[kSchema]) {
      schema.inner = schema.builder();
      schema.inner.meta = {
        ...schema.meta,
        ...schema.inner.meta
      };
    }
    return schema.inner.toJSON();
  };
  const schema = new Schema({
    type: "lazy",
    builder,
    inner: { toJSON: toJSON2 }
  });
  return schema;
};
Schema.natural = function natural() {
  return Schema.number().step(1).min(0);
};
Schema.percent = function percent() {
  return Schema.number().step(0.01).min(0).max(1).role("slider");
};
Schema.date = function date() {
  return Schema.union([Schema.is(Date), Schema.transform(Schema.string().role("datetime"), (value, options) => {
    const date2 = new Date(value);
    if (isNaN(+date2)) throw new ValidationError(`invalid date "${value}"`, options);
    return date2;
  }, true)]);
};
Schema.regExp = function regExp(flag = "") {
  return Schema.union([Schema.is(RegExp), Schema.transform(Schema.string().role("regexp", { flag }), (value, options) => {
    try {
      return new RegExp(value, flag);
    } catch (e) {
      throw new ValidationError(e.message, options);
    }
  }, true)]);
};
Schema.arrayBuffer = function arrayBuffer(encoding) {
  return Schema.union([
    Schema.is(ArrayBuffer),
    Schema.is(SharedArrayBuffer),
    Schema.transform(Schema.any(), (value, options) => {
      if (Binary.isSource(value)) return Binary.fromSource(value);
      throw new ValidationError(`expected ArrayBufferSource but got ${value}`, options);
    }, true),
    ...encoding ? [Schema.transform(Schema.string(), (value, options) => {
      try {
        return encoding === "base64" ? Binary.fromBase64(value) : Binary.fromHex(value);
      } catch (e) {
        throw new ValidationError(e.message, options);
      }
    }, true)] : []
  ]);
};
Schema.extend("lazy", (data, schema, options, strict) => {
  if (!schema.inner[kSchema]) {
    schema.inner = schema.builder();
    schema.inner.meta = {
      ...schema.meta,
      ...schema.inner.meta
    };
    validateVolatileSchema(schema.inner, options.path, true);
  }
  return Schema.resolve(data, schema.inner, options, strict);
});
Schema.extend("any", (data) => {
  return [data];
});
Schema.extend("never", (data, _, options) => {
  throw new ValidationError(`expected nullable but got ${data}`, options);
});
Schema.extend("const", (data, { value }, options) => {
  if (deepEqual(data, value)) return [value];
  throw new ValidationError(`expected ${value} but got ${data}`, options);
});
function checkWithinRange(data, meta, description, options, skipMin = false) {
  const { max = Infinity, min = -Infinity } = meta;
  if (data > max) throw new ValidationError(`expected ${description} <= ${max} but got ${data}`, options);
  if (data < min && !skipMin) throw new ValidationError(`expected ${description} >= ${min} but got ${data}`, options);
}
Schema.extend("string", (data, { meta }, options) => {
  if (typeof data !== "string") throw new ValidationError(`expected string but got ${data}`, options);
  if (meta.pattern) {
    const regexp = new RegExp(meta.pattern.source, meta.pattern.flags);
    if (!regexp.test(data)) throw new ValidationError(`expect string to match regexp ${regexp}`, options);
  }
  checkWithinRange(data.length, meta, "string length", options);
  return [data];
});
function decimalShift(data, digits) {
  const str = data.toString();
  if (str.includes("e")) return data * Math.pow(10, digits);
  const index = str.indexOf(".");
  if (index === -1) return data * Math.pow(10, digits);
  const frac = str.slice(index + 1);
  const integer = str.slice(0, index);
  if (frac.length <= digits) return +(integer + frac.padEnd(digits, "0"));
  return +(integer + frac.slice(0, digits) + "." + frac.slice(digits));
}
function isMultipleOf(data, min, step) {
  step = Math.abs(step);
  if (!/^\d+\.\d+$/.test(step.toString())) return (data - min) % step === 0;
  const index = step.toString().indexOf(".");
  const digits = step.toString().slice(index + 1).length;
  return Math.abs(decimalShift(data, digits) - decimalShift(min, digits)) % decimalShift(step, digits) === 0;
}
Schema.extend("number", (data, { meta }, options) => {
  if (typeof data !== "number") throw new ValidationError(`expected number but got ${data}`, options);
  checkWithinRange(data, meta, "number", options);
  const { step } = meta;
  if (step && !isMultipleOf(data, meta.min ?? 0, step)) throw new ValidationError(`expected number multiple of ${step} but got ${data}`, options);
  return [data];
});
Schema.extend("boolean", (data, _, options) => {
  if (typeof data === "boolean") return [data];
  throw new ValidationError(`expected boolean but got ${data}`, options);
});
Schema.extend("bitset", (data, { bits, meta }, options) => {
  let value = 0, keys = [];
  if (typeof data === "number") {
    value = data;
    for (const key in bits) if (data & bits[key]) keys.push(key);
  } else if (Array.isArray(data)) {
    keys = data;
    for (const key of keys) {
      if (typeof key !== "string") throw new ValidationError(`expected string but got ${key}`, options);
      if (key in bits) value |= bits[key];
    }
  } else throw new ValidationError(`expected number or array but got ${data}`, options);
  if (value === meta.default) return [value];
  return [value, keys];
});
Schema.extend("function", (data, _, options) => {
  if (typeof data === "function") return [data];
  throw new ValidationError(`expected function but got ${data}`, options);
});
Schema.extend("is", (data, { constructor }, options) => {
  if (typeof constructor === "function") {
    if (data instanceof constructor) return [data];
    throw new ValidationError(`expected ${constructor.name} but got ${data}`, options);
  } else {
    if (isNullable(data)) throw new ValidationError(`expected ${constructor} but got ${data}`, options);
    let prototype = Object.getPrototypeOf(data);
    while (prototype) {
      if (prototype.constructor?.name === constructor) return [data];
      prototype = Object.getPrototypeOf(prototype);
    }
    throw new ValidationError(`expected ${constructor} but got ${data}`, options);
  }
});
function property(data, key, schema, options) {
  try {
    const [value, adapted] = Schema.resolve(data[key], schema, {
      ...options,
      path: [...options.path || [], key]
    });
    if (adapted !== void 0) data[key] = adapted;
    return value;
  } catch (e) {
    if (!options?.autofix) throw e;
    delete data[key];
    return schema.meta.volatile ? createVolatile(schema.meta.default) : schema.meta.default;
  }
}
Schema.extend("array", (data, { inner, meta }, options) => {
  if (!Array.isArray(data)) throw new ValidationError(`expected array but got ${data}`, options);
  checkWithinRange(data.length, meta, "array length", options, !isNullable(inner.meta.default));
  return [data.map((_, index) => property(data, index, inner, options))];
});
Schema.extend("dict", (data, { inner, sKey }, options, strict) => {
  if (!isPlainObject(data)) throw new ValidationError(`expected object but got ${data}`, options);
  const result = {};
  for (const key in data) {
    let rKey;
    try {
      rKey = Schema.resolve(key, sKey, options)[0];
    } catch (error) {
      if (strict) continue;
      throw error;
    }
    result[rKey] = property(data, key, inner, options);
    data[rKey] = data[key];
    if (key !== rKey) delete data[key];
  }
  return [result];
});
Schema.extend("tuple", (data, { list }, options, strict) => {
  if (!Array.isArray(data)) throw new ValidationError(`expected array but got ${data}`, options);
  const result = list.map((inner, index) => property(data, index, inner, options));
  if (strict) return [result];
  result.push(...data.slice(list.length));
  return [result];
});
function merge(result, data) {
  for (const key in data) {
    if (key in result) continue;
    result[key] = data[key];
  }
}
Schema.extend("object", (data, { dict }, options, strict) => {
  if (!isPlainObject(data)) throw new ValidationError(`expected object but got ${data}`, options);
  const result = {};
  for (const key in dict) {
    const value = property(data, key, dict[key], options);
    if (!isNullable(value) || key in data) result[key] = value;
  }
  if (!strict) merge(result, data);
  return [result];
});
Schema.extend("union", (data, { list, toString: toString2 }, options, strict) => {
  const messages = [];
  for (const inner of list) try {
    return Schema.resolve(data, inner, options, strict);
  } catch (error) {
    messages.push(error);
  }
  throw new ValidationError(`expected ${toString2()} but got ${JSON.stringify(data)}`, options);
});
Schema.extend("intersect", (data, { list, toString: toString2 }, options, strict) => {
  if (!list.length) return [data];
  let result;
  for (const inner of list) {
    const value = Schema.resolve(data, inner, options, true)[0];
    if (isNullable(value)) continue;
    if (isNullable(result)) result = value;
    else if (typeof result !== typeof value) throw new ValidationError(`expected ${toString2()} but got ${JSON.stringify(data)}`, options);
    else if (typeof value === "object") merge(result ??= {}, value);
    else if (result !== value) throw new ValidationError(`expected ${toString2()} but got ${JSON.stringify(data)}`, options);
  }
  if (!strict && isPlainObject(data)) merge(result, data);
  return [result];
});
Schema.extend("transform", (data, { inner, callback, preserve }, options) => {
  const [result, adapted = data] = Schema.resolve(data, inner, options, true);
  if (preserve) return [callback(result)];
  else return [callback(result), callback(adapted)];
});
var formatters = {};
function defineMethod(name2, keys, format) {
  formatters[name2] = format;
  Object.assign(Schema, { [name2](...args) {
    const schema = new Schema({ type: name2 });
    keys.forEach((key, index) => {
      switch (key) {
        case "sKey":
          schema.sKey = args[index] ?? Schema.string();
          break;
        case "inner":
          schema.inner = Schema.from(args[index]);
          break;
        case "list":
          schema.list = args[index].map(Schema.from);
          break;
        case "dict":
          schema.dict = mapValues(args[index], Schema.from);
          break;
        case "bits":
          schema.bits = {};
          for (const key2 in args[index]) {
            if (typeof args[index][key2] !== "number") continue;
            schema.bits[key2] = args[index][key2];
          }
          break;
        case "callback": {
          const callback = schema.callback = args[index];
          callback["toJSON"] ||= () => callback.toString();
          break;
        }
        case "constructor": {
          const constructor = schema.constructor = args[index];
          if (typeof constructor === "function") constructor["toJSON"] ||= () => constructor["name"];
          break;
        }
        default:
          schema[key] = args[index];
      }
    });
    if (name2 === "object" || name2 === "dict") schema.meta.default = {};
    else if (name2 === "array" || name2 === "tuple") schema.meta.default = [];
    else if (name2 === "bitset") schema.meta.default = 0;
    return schema;
  } });
}
defineMethod("is", ["constructor"], ({ constructor }) => {
  if (typeof constructor === "function") return constructor.name;
  else return constructor;
});
defineMethod("any", [], () => "any");
defineMethod("never", [], () => "never");
defineMethod("const", ["value"], ({ value }) => typeof value === "string" ? JSON.stringify(value) : value);
defineMethod("string", [], () => "string");
defineMethod("number", [], () => "number");
defineMethod("boolean", [], () => "boolean");
defineMethod("bitset", ["bits"], () => "bitset");
defineMethod("function", [], () => "function");
defineMethod("array", ["inner"], ({ inner }) => `${inner.toString(true)}[]`);
defineMethod("dict", ["inner", "sKey"], ({ inner, sKey }) => `{ [key: ${sKey.toString()}]: ${inner.toString()} }`);
defineMethod("tuple", ["list"], ({ list }) => `[${list.map((inner) => inner.toString()).join(", ")}]`);
defineMethod("object", ["dict"], ({ dict }) => {
  if (Object.keys(dict).length === 0) return "{}";
  return `{ ${Object.entries(dict).map(([key, inner]) => {
    return `${key}${inner.meta.required ? "" : "?"}: ${inner.toString()}`;
  }).join(", ")} }`;
});
defineMethod("union", ["list"], ({ list }, inline) => {
  const result = list.map(({ toString: format }) => format()).join(" | ");
  return inline ? `(${result})` : result;
});
defineMethod("intersect", ["list"], ({ list }) => {
  return `${list.map((inner) => inner.toString(true)).join(" & ")}`;
});
defineMethod("transform", [
  "inner",
  "callback",
  "preserve"
], ({ inner }, isInner) => inner.toString(isInner));

// src/plugin/shared/settings.js
var SETTINGS_NAMESPACE = "coderag";
var BUNDLE_NAME = "dsh-coderag";
var MCP_ROW_ID = "mcp-coderag";
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
function valuesFromConfig(config) {
  const values = {};
  for (const field of FIELDS) {
    const slot = config?.[field.key];
    values[field.key] = typeof slot?.get === "function" ? slot.get() : slot;
  }
  return normalizeValues(values);
}
function isEmptySettings(values) {
  const normalized = normalizeValues(values);
  return normalized.root === "" && normalized.extraExtensions === "" && !normalized.semantic && normalized.maxFiles === 0 && normalized.maxFileBytes === 0 && normalized.maxTokens === 0 && normalized.semanticBackend === "" && normalized.semanticUrl === "" && normalized.semanticModel === "" && normalized.semanticTimeout === 0 && normalized.semanticBatch === 0 && normalized.semanticMaxChunks === 0 && !normalized.semanticAllowRemote;
}
function envPlan(values) {
  const normalized = normalizeValues(values);
  const set2 = {};
  const remove = [];
  for (const field of FIELDS) {
    if (field.env === void 0) continue;
    const value = normalized[field.key];
    const text2 = field.kind === "boolean" ? value === true ? field.envTrue ?? "on" : "" : String(value);
    if (text2 === "" || value === 0) remove.push(field.env);
    else set2[field.env] = text2;
  }
  return { set: set2, remove };
}
function mergeOwnedEnv(currentEnv, values) {
  const next = currentEnv !== null && typeof currentEnv === "object" ? { ...currentEnv } : {};
  const plan = envPlan(values);
  for (const name2 of plan.remove) delete next[name2];
  for (const [name2, value] of Object.entries(plan.set)) next[name2] = value;
  return next;
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
function normalizeHealth(raw) {
  const source = raw !== null && typeof raw === "object" ? raw : {};
  return {
    ok: source.ok === true,
    backend: text(source.backend) ?? "",
    url: text(source.url) ?? "",
    model: text(source.model) ?? "",
    model_present: source.model_present === true,
    detail: text(source.detail) ?? "",
    models: Array.isArray(source.models) ? source.models.flatMap((entry) => typeof entry === "string" && entry.length > 0 ? [entry] : entry !== null && typeof entry === "object" && typeof entry.name === "string" && entry.name.length > 0 ? [entry.name] : []) : []
  };
}
function adminError(code, message) {
  return { code, message };
}

// src/plugin/sync.js
function findMCPEntry(loader) {
  if (loader === void 0 || typeof loader.entries !== "function") return void 0;
  for (const entry of loader.entries()) {
    if (entry?.options?.id === MCP_ROW_ID) return entry;
  }
  return void 0;
}
function ownedEnvMismatch(env, plan) {
  const source = env !== null && typeof env === "object" ? env : {};
  for (const name2 of plan.remove) {
    if (source[name2] !== void 0) return true;
  }
  for (const [name2, value] of Object.entries(plan.set)) {
    if (source[name2] !== value) return true;
  }
  return false;
}
function rawEnv(config) {
  if (config === null || typeof config !== "object") return {};
  const env = Reflect.get(config, "env");
  return env !== null && typeof env === "object" && !Array.isArray(env) ? screenEnv(env) : {};
}
function screenEnv(env) {
  return { ...env };
}
async function syncMCPRow(entry, values, options = {}) {
  const plan = envPlan(values);
  const apiKey = options.apiKey;
  if (typeof apiKey === "string" && apiKey !== "") plan.set[SEMANTIC_KEY_REF] = apiKey;
  const nextEnv = mergeOwnedEnv(rawEnv(entry.options?.config), values);
  if (typeof apiKey === "string" && apiKey !== "") nextEnv[SEMANTIC_KEY_REF] = apiKey;
  const rawChanged = ownedEnvMismatch(rawEnv(entry.options?.config), plan);
  const liveEnv = () => entry.fiber !== void 0 ? entry.fiber.config?.env : void 0;
  const liveChanged = entry.fiber !== void 0 && entry.fiber.config !== void 0 && ownedEnvMismatch(liveEnv(), plan);
  if (!rawChanged && !liveChanged) return "unchanged";
  const nextConfig = { ...entry.options?.config ?? {}, env: nextEnv };
  await entry.update({ config: nextConfig });
  if (entry.fiber === void 0) return "synced";
  await entry.fiber.await();
  if (!entry.fiber.config || !ownedEnvMismatch(liveEnv(), plan)) return "synced";
  entry.fiber.update(nextConfig, true);
  await entry.fiber.await();
  return "forced";
}

// src/plugin/host/admin.js
import { spawn as nodeSpawn } from "node:child_process";
import { tmpdir } from "node:os";
var COMMAND_TIMEOUT_MS = 3e4;
var LOCAL_START_TIMEOUT_MS = 15e3;
var LOCAL_POLL_INTERVAL_MS = 500;
var LOCAL_PROBE_TIMEOUT_MS = 1500;
var STDERR_LIMIT = 8 * 1024;
var ERROR_EXCERPT = 400;
var DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434";
function parseJsonOutput(text2) {
  const trimmed = text2.trim();
  if (trimmed === "") return void 0;
  try {
    return JSON.parse(trimmed);
  } catch {
    const lines = trimmed.split(/\r?\n/);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index].trim();
      if (!line.startsWith("{")) continue;
      try {
        return JSON.parse(line);
      } catch {
      }
    }
    return void 0;
  }
}
function lineReader(onLine) {
  let buffer = "";
  return {
    push(chunk) {
      buffer += chunk.toString("utf8");
      for (; ; ) {
        const newline = buffer.indexOf("\n");
        if (newline < 0) return;
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line !== "") onLine(line);
      }
    }
  };
}
function scrub(value, secret) {
  if (secret === void 0 || secret === "") return value;
  return value.split(secret).join("[redacted]");
}
function excerpt(value) {
  const text2 = String(value ?? "").replace(/\s+/g, " ").trim();
  return text2.length > ERROR_EXCERPT ? `${text2.slice(0, ERROR_EXCERPT)}…` : text2;
}
function adminEnvironment(values, apiKey, backend, forceSemantic = false) {
  const plan = envPlan(values);
  const env = {
    ...process.env,
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
    ...plan.set
  };
  for (const name2 of plan.remove) delete env[name2];
  if (forceSemantic) env.CODERAG_SEMANTIC = "on";
  if (backend !== void 0 && HEALTH_BACKENDS.includes(backend)) {
    env.CODERAG_SEMANTIC_BACKEND = backend;
  }
  if (apiKey !== void 0 && apiKey !== "") env[SEMANTIC_KEY_REF] = apiKey;
  return env;
}
function createAdminService(options) {
  const spawn = options.spawn ?? nodeSpawn;
  const fetchImpl = options.fetch ?? globalThis.fetch;
  const sleep = options.sleep ?? ((ms) => new Promise((resolve2) => setTimeout(resolve2, ms)));
  const now = options.now ?? (() => Date.now());
  const logger = options.logger;
  let job = emptyJob();
  let active;
  const rootOf = () => {
    const root = options.readValues().root;
    return typeof root === "string" ? root.trim() : "";
  };
  const pythonOf = () => {
    const configured = options.python?.();
    if (typeof configured === "string" && configured.trim() !== "") return configured.trim();
    return process.platform === "win32" ? "python" : "python3";
  };
  const snapshot2 = () => ({
    ...job,
    error: job.error === null ? null : { ...job.error }
  });
  async function runOnce(args, config) {
    const command = pythonOf();
    const env = adminEnvironment(options.readValues(), config.apiKey, config.backend, config.forceSemantic === true);
    return new Promise((resolve2) => {
      let settled = false;
      let stdout = "";
      let stderr = "";
      let child;
      const finish = (result) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (result.ok === false) {
          const message = scrub(result.error.message, config.apiKey);
          resolve2({ ok: false, error: adminError(result.error.code, excerpt(message)) });
          return;
        }
        const parsed = parseJsonOutput(stdout);
        resolve2(parsed === void 0 ? { ok: false, error: adminError("admin-output-invalid", "admin 输出不是 JSON") } : { ok: true, value: parsed });
      };
      const timer = setTimeout(() => {
        child?.kill("SIGTERM");
        finish({ ok: false, error: { code: "admin-timeout", message: `admin 命令超过 ${config.timeoutMs}ms` } });
      }, config.timeoutMs);
      try {
        child = spawn(command, ["-m", "dsh_coderag.admin", ...args], {
          cwd: tmpdir(),
          env,
          stdio: ["ignore", "pipe", "pipe"],
          windowsHide: true
        });
      } catch (error) {
        finish({ ok: false, error: { code: "admin-spawn-failed", message: String(error?.message ?? error) } });
        return;
      }
      child.on("error", (error) => {
        finish({ ok: false, error: { code: "admin-spawn-failed", message: String(error?.message ?? error) } });
      });
      child.stdout.on("data", (chunk) => {
        stdout += chunk.toString("utf8");
      });
      child.stderr.on("data", (chunk) => {
        if (stderr.length < STDERR_LIMIT) stderr += chunk.toString("utf8");
      });
      child.on("close", (code) => {
        if (code === 0) {
          finish({ ok: true });
          return;
        }
        const reported = parseJsonOutput(stdout);
        if (reported !== null && typeof reported === "object" && reported.ok === false) {
          finish({
            ok: false,
            error: {
              code: typeof reported.code === "string" ? reported.code : "admin-failed",
              message: typeof reported.message === "string" ? reported.message : stderr || `admin 退出码 ${String(code)}`
            }
          });
          return;
        }
        finish({ ok: false, error: { code: "admin-failed", message: stderr || `admin 退出码 ${String(code)}` } });
      });
    });
  }
  async function currentKey() {
    try {
      return await options.resolveApiKey();
    } catch (error) {
      logger?.warn?.("coderag: credentials lookup failed");
      logger?.warn?.(error);
      return void 0;
    }
  }
  function requireRoot() {
    const root = rootOf();
    return root === "" ? { ok: false, error: adminError("root-unset", "请先在设置里填写工作区根并保存") } : { ok: true, root };
  }
  return {
    /** Current job snapshot (no child handle). */
    job: () => snapshot2(),
    /** Read index/vector facts for the saved root. */
    async state() {
      const required = requireRoot();
      if (required.ok === false) return required;
      const key = await currentKey();
      const result = await runOnce(["status", "--root", required.root], { timeoutMs: COMMAND_TIMEOUT_MS, apiKey: key });
      if (result.ok === false) return result;
      return { ok: true, value: normalizeAdminStatus(result.value) };
    },
    /** Probe the embedding backend; `backend` overrides the saved one. */
    async health(backend) {
      const root = rootOf();
      const key = await currentKey();
      const result = await runOnce(["health", "--root", root], {
        timeoutMs: COMMAND_TIMEOUT_MS,
        apiKey: key,
        backend: HEALTH_BACKENDS.includes(backend) ? backend : void 0,
        forceSemantic: true
      });
      if (result.ok === false) return result;
      return { ok: true, value: normalizeHealth(result.value) };
    },
    /**
     * Start `ollama serve` detached and wait until its API answers.
     * An already-running server makes the poll succeed immediately.
     */
    async startLocal() {
      const values = options.readValues();
      const configuredUrl = typeof values.semanticUrl === "string" ? values.semanticUrl.trim().replace(/\/+$/, "") : "";
      const url = configuredUrl !== "" && values.semanticBackend !== "openai" ? configuredUrl : DEFAULT_OLLAMA_URL;
      let child;
      try {
        child = spawn("ollama", ["serve"], {
          detached: true,
          stdio: "ignore",
          windowsHide: true,
          env: process.env
        });
        child.on("error", () => {
        });
        child.unref();
      } catch (error) {
        return {
          ok: false,
          error: adminError("ollama-missing", `无法启动 ollama serve：${excerpt(error?.message ?? error)}`)
        };
      }
      const deadline = now() + LOCAL_START_TIMEOUT_MS;
      let lastDetail = "";
      while (now() < deadline) {
        try {
          const response = await fetchImpl(`${url}/api/tags`, { signal: AbortSignal.timeout(LOCAL_PROBE_TIMEOUT_MS) });
          if (response.ok) {
            const body = await response.json().catch(() => void 0);
            const models = Array.isArray(body?.models) ? body.models.flatMap((entry) => typeof entry?.name === "string" ? [entry.name] : []) : [];
            return { ok: true, value: { url, models } };
          }
          lastDetail = `HTTP ${String(response.status)}`;
        } catch (error) {
          lastDetail = excerpt(error?.message ?? error);
        }
        await sleep(LOCAL_POLL_INTERVAL_MS);
      }
      child?.kill?.("SIGTERM");
      return {
        ok: false,
        error: adminError(
          "ollama-unreachable",
          `已启动 ollama serve，但 ${String(Math.round(LOCAL_START_TIMEOUT_MS / 1e3))} 秒内 ${url}/api/tags 未就绪${lastDetail === "" ? "" : `（最后错误：${lastDetail}）`}`
        )
      };
    },
    /** Start a resumable vector build; progress is reported through `job()`. */
    async vectorize() {
      const required = requireRoot();
      if (required.ok === false) return required;
      if (job.status === "running" || job.status === "stopping") {
        return { ok: false, error: adminError("job-running", "已有向量化任务在运行") };
      }
      const key = await currentKey();
      const command = pythonOf();
      const env = adminEnvironment(options.readValues(), key);
      job = {
        ...emptyJob(),
        status: "running",
        startedAt: now()
      };
      let child;
      try {
        child = spawn(command, ["-m", "dsh_coderag.admin", "vectorize", "--root", required.root], {
          cwd: tmpdir(),
          env,
          stdio: ["ignore", "pipe", "pipe"],
          windowsHide: true
        });
      } catch (error) {
        job = { ...job, status: "error", finishedAt: now(), error: adminError("admin-spawn-failed", excerpt(error?.message ?? error)) };
        return { ok: true, value: snapshot2() };
      }
      active = { child, stopRequested: false, key };
      let stderr = "";
      const applyEvent = (line) => {
        let event;
        try {
          event = JSON.parse(line);
        } catch {
          return;
        }
        if (event === null || typeof event !== "object") return;
        if (event.event === "start") {
          job = {
            ...job,
            total: typeof event.total_chunks === "number" ? event.total_chunks : job.total,
            pending: typeof event.pending_chunks === "number" ? event.pending_chunks : job.pending
          };
          return;
        }
        if (event.event === "progress") {
          job = {
            ...job,
            status: "running",
            embedded: typeof event.embedded === "number" ? event.embedded : job.embedded,
            pending: typeof event.pending === "number" ? event.pending : job.pending
          };
          return;
        }
        if (event.event === "done") {
          job = {
            ...job,
            status: "done",
            embedded: typeof event.chunks === "number" ? event.chunks : job.embedded,
            pending: 0,
            model: typeof event.model === "string" ? event.model : job.model,
            generatedAt: typeof event.generated_at === "string" ? event.generated_at : job.generatedAt,
            finishedAt: now()
          };
          return;
        }
        if (event.event === "error") {
          job = {
            ...job,
            status: "error",
            error: adminError(
              typeof event.code === "string" ? event.code : "vectorize-failed",
              scrub(typeof event.message === "string" ? event.message : "向量化失败", key)
            )
          };
        }
      };
      const out = lineReader(applyEvent);
      child.stdout.on("data", (chunk) => out.push(chunk));
      child.stderr.on("data", (chunk) => {
        if (stderr.length < STDERR_LIMIT) stderr += chunk.toString("utf8");
      });
      child.on("error", (error) => {
        if (job.status === "done") return;
        job = {
          ...job,
          status: "error",
          finishedAt: now(),
          error: adminError("admin-spawn-failed", scrub(excerpt(error?.message ?? error), key))
        };
      });
      child.on("close", (code) => {
        const stopped = active?.stopRequested === true;
        active = void 0;
        if (job.status === "done") return;
        if (stopped) {
          job = { ...job, status: "stopped", finishedAt: now(), error: null };
          return;
        }
        job = code === 0 ? { ...job, status: "done", pending: 0, finishedAt: now() } : {
          ...job,
          status: "error",
          finishedAt: now(),
          error: job.error ?? adminError("vectorize-failed", scrub(stderr || `admin 退出码 ${String(code)}`, key))
        };
      });
      return { ok: true, value: snapshot2() };
    },
    /** Ask the running build to stop; the CLI's checkpoint stays on disk. */
    stop() {
      if (active === void 0 || job.status !== "running" && job.status !== "stopping") {
        return { ok: true, value: snapshot2() };
      }
      active.stopRequested = true;
      job = { ...job, status: "stopping" };
      try {
        active.child.kill("SIGTERM");
      } catch (error) {
        logger?.warn?.("coderag: could not stop the vectorize child");
        logger?.warn?.(error);
      }
      const force = setTimeout(() => {
        try {
          active?.child.kill("SIGKILL");
        } catch {
        }
      }, 5e3);
      force.unref?.();
      return { ok: true, value: snapshot2() };
    }
  };
}

// src/plugin/host/credentials.js
async function resolveApiKey(ctx) {
  const credentials = ctx.get("credentials");
  if (credentials === void 0 || typeof credentials.resolve !== "function") return void 0;
  const resolved = await credentials.resolve(SEMANTIC_KEY_REF);
  const value = resolved?.value;
  return typeof value === "string" && value !== "" ? value : void 0;
}

// src/plugin/host/routes.js
var MAX_BODY_BYTES = 64 * 1024;
function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(payload));
}
function methodNotAllowed(res, allow) {
  res.statusCode = 405;
  res.setHeader("allow", allow);
  res.end();
}
async function readBoundedBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.byteLength;
    if (size > MAX_BODY_BYTES) {
      req.resume();
      return null;
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks, size).toString("utf8");
}
function parseActionBody(text2) {
  let body;
  try {
    body = JSON.parse(text2);
  } catch {
    return void 0;
  }
  if (body === null || typeof body !== "object") return void 0;
  const { action, backend } = body;
  if (typeof action !== "string" || !ADMIN_ACTIONS.includes(action)) return void 0;
  if (backend !== void 0 && (typeof backend !== "string" || !HEALTH_BACKENDS.includes(backend))) return void 0;
  return backend === void 0 ? { action } : { action, backend };
}
function createAdminHttp(admin, hooks = {}) {
  return {
    async state(req, res) {
      if (req.method !== "GET") {
        methodNotAllowed(res, "GET");
        return;
      }
      sendJson(res, 200, await admin.state());
    },
    async job(req, res) {
      if (req.method !== "GET") {
        methodNotAllowed(res, "GET");
        return;
      }
      sendJson(res, 200, { ok: true, value: admin.job() });
    },
    async action(req, res) {
      if (req.method !== "POST") {
        methodNotAllowed(res, "POST");
        return;
      }
      const essence = String(req.headers["content-type"]).split(";", 1)[0]?.trim().toLowerCase();
      if (essence !== "application/json") {
        sendJson(res, 415, { ok: false, error: adminError("unsupported-media-type", "content-type must be application/json") });
        return;
      }
      let text2;
      try {
        text2 = await readBoundedBody(req);
      } catch (error) {
        sendJson(res, 400, { ok: false, error: adminError("body-unreadable", String(error?.message ?? error)) });
        return;
      }
      const parsed = text2 === null ? void 0 : parseActionBody(text2);
      if (parsed === void 0) {
        sendJson(res, 400, { ok: false, error: adminError("bad-action", "请求体必须是 {action} 且 action 在允许列表内") });
        return;
      }
      try {
        switch (parsed.action) {
          case "health":
            sendJson(res, 200, await admin.health(parsed.backend));
            return;
          case "start-local":
            sendJson(res, 200, await admin.startLocal());
            return;
          case "vectorize":
            sendJson(res, 200, await admin.vectorize());
            return;
          case "stop":
            sendJson(res, 200, admin.stop());
            return;
          case "refresh":
            await hooks.syncNow?.();
            sendJson(res, 200, { ok: true, value: admin.job() });
            return;
          default:
            sendJson(res, 400, { ok: false, error: adminError("bad-action", `unsupported action ${String(parsed.action)}`) });
        }
      } catch (error) {
        sendJson(res, 500, { ok: false, error: adminError("admin-internal", String(error?.message ?? error)) });
      }
    }
  };
}
function rejected(connection, req, res) {
  const rejection = connection.requestRejection(req);
  if (rejection === void 0) return false;
  res.statusCode = rejection;
  res.end();
  return true;
}
function registerAdminRoutes(ctx, deps) {
  ctx.inject(["webServer", "connection"], (sctx) => {
    const http = createAdminHttp(deps.admin, { syncNow: deps.syncNow });
    const connection = sctx.connection;
    const routes = [
      { path: ADMIN_STATE_PATH, handler: http.state, label: "GET" },
      { path: ADMIN_ACTION_PATH, handler: http.action, label: "POST" },
      { path: ADMIN_JOB_PATH, handler: http.job, label: "GET" }
    ];
    for (const route of routes) {
      sctx.effect(() => sctx.webServer.register({
        kind: "exact",
        path: route.path,
        handler: (req, res) => {
          if (rejected(connection, req, res)) return;
          return route.handler(req, res);
        }
      }), `coderag: ${route.label} ${route.path}`);
    }
  });
}

// src/plugin/index.js
var name = "dsh-coderag";
var inject = ["loader"];
var Config = Schema.object({
  root: Schema.string().default(DEFAULT_VALUES.root).description("Workspace root the engine indexes.").volatile(),
  maxFiles: Schema.natural().default(DEFAULT_VALUES.maxFiles).description("File cap; 0 uses the engine default.").volatile(),
  maxFileBytes: Schema.natural().default(DEFAULT_VALUES.maxFileBytes).description("Per-file byte cap; 0 uses the engine default.").volatile(),
  maxTokens: Schema.natural().default(DEFAULT_VALUES.maxTokens).description("Search token budget; 0 uses the engine default (4000).").volatile(),
  extraExtensions: Schema.string().default(DEFAULT_VALUES.extraExtensions).description("Extra extensions, comma or space separated.").volatile(),
  semantic: Schema.boolean().default(DEFAULT_VALUES.semantic).description("Enable the optional semantic backend.").volatile(),
  semanticBackend: Schema.union([Schema.const(""), Schema.const("ollama"), Schema.const("openai")]).default(DEFAULT_VALUES.semanticBackend).description("Embedding backend; empty uses the engine default (ollama).").volatile(),
  semanticUrl: Schema.string().default(DEFAULT_VALUES.semanticUrl).description("Embedding service URL.").volatile(),
  semanticModel: Schema.string().default(DEFAULT_VALUES.semanticModel).description("Embedding model name.").volatile(),
  semanticTimeout: Schema.natural().default(DEFAULT_VALUES.semanticTimeout).description("Request timeout in seconds; 0 uses the default.").volatile(),
  semanticBatch: Schema.natural().default(DEFAULT_VALUES.semanticBatch).description("Embedding batch size; 0 uses the default.").volatile(),
  semanticMaxChunks: Schema.natural().default(DEFAULT_VALUES.semanticMaxChunks).description("Embedding chunk cap; 0 uses the engine default.").volatile(),
  semanticAllowRemote: Schema.boolean().default(DEFAULT_VALUES.semanticAllowRemote).description("Allow a non-loopback cloud embedding URL (second opt-in).").volatile()
});
var INITIAL_SYNC_ATTEMPTS = 40;
var INITIAL_SYNC_INTERVAL_MS = 100;
function createSyncQueue(ctx, read) {
  let tail = Promise.resolve();
  const run = () => {
    tail = tail.then(async () => {
      const loader = ctx.get("loader");
      const entry = findMCPEntry(loader);
      if (entry === void 0) return "missing";
      let apiKey;
      try {
        apiKey = await resolveApiKey(ctx);
      } catch (error) {
        ctx.logger?.warn("coderag: could not resolve the cloud API key; keeping the current env value");
        ctx.logger?.warn(error);
      }
      const outcome = await syncMCPRow(entry, read(), { apiKey });
      if (outcome !== "unchanged") {
        ctx.logger?.info("coderag: settings synced to the mcp-coderag row (%s)", outcome);
      }
      return outcome;
    }).catch((error) => {
      ctx.logger?.warn("coderag: failed to sync the mcp-coderag row");
      ctx.logger?.warn(error);
      return "failed";
    });
    return tail;
  };
  return { run };
}
function interpreterOf(ctx) {
  const entry = findMCPEntry(ctx.get("loader"));
  const command = entry?.fiber?.config?.command;
  return typeof command === "string" && command.trim() !== "" ? command.trim() : void 0;
}
function apply(ctx, config) {
  const read = () => valuesFromConfig(config);
  const queue = createSyncQueue(ctx, read);
  const admin = createAdminService({
    readValues: read,
    resolveApiKey: () => resolveApiKey(ctx),
    python: () => interpreterOf(ctx),
    logger: ctx.logger
  });
  registerAdminRoutes(ctx, { admin, syncNow: () => queue.run() });
  ctx.on("loader/volatile-update", () => {
    void queue.run();
  });
  ctx.on("loader/entry-init", (entry) => {
    if (entry?.options?.id !== MCP_ROW_ID) return;
    queueMicrotask(() => {
      void queue.run();
    });
  });
  const initial = read();
  if (!isEmptySettings(initial)) {
    ctx.effect(() => {
      let attempts = 0;
      let timer;
      let disposed = false;
      const tick = async () => {
        if (disposed) return;
        const entry = findMCPEntry(ctx.get("loader"));
        if (entry !== void 0) {
          if (entry.fiber !== void 0) await entry.fiber.await();
          const outcome = await queue.run();
          if (outcome !== "missing") return;
        }
        attempts += 1;
        if (attempts >= INITIAL_SYNC_ATTEMPTS) {
          ctx.logger?.warn("coderag: mcp-coderag row was not found; settings cannot reach the engine");
          return;
        }
        timer = setTimeout(() => {
          void tick();
        }, INITIAL_SYNC_INTERVAL_MS);
      };
      timer = setTimeout(() => {
        void tick();
      }, 0);
      return () => {
        disposed = true;
        clearTimeout(timer);
      };
    }, "coderag: initial settings sync");
  }
  ctx.inject(["settings"], (sctx) => sctx.effect(
    () => sctx.settings.configure({ auto: false }, ctx.fiber),
    "coderag: own the settings page"
  ));
  ctx.effect(() => {
    if (!validateValues(read()).length) return;
    ctx.logger?.warn("coderag: current settings would be rejected by the browser form (cloud backend needs URL and model)");
  }, "coderag: cross-field settings check");
}
export {
  Config,
  apply,
  inject,
  name
};
