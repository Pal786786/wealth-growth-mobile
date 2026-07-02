/**
 * Centralised error / value stringification utilities.
 *
 * WHY:
 *   Backends return validation errors and gated responses (like KYC_REQUIRED)
 *   as OBJECT payloads under `response.data.detail`. If any UI component
 *   naively renders these directly inside <Text>, React crashes with:
 *
 *     Objects are not valid as a React child.
 *
 *   Every catch handler in the app used to look like:
 *
 *     show("error", e?.response?.data?.detail || e?.message || "...")
 *
 *   ...which passed an object to <Text> whenever detail was structured.
 *
 * Use `errText(e, fallback)` in every catch block, and `safeStr(x)` anywhere
 * you're rendering an unknown / user-derived value inside <Text>.
 */

export function safeStr(x: any, fallback = ""): string {
  if (x === null || x === undefined) return fallback;
  if (typeof x === "string") return x;
  if (typeof x === "number" || typeof x === "boolean" || typeof x === "bigint") return String(x);
  if (Array.isArray(x)) {
    return x.map((v) => safeStr(v, "")).filter(Boolean).join(", ") || fallback;
  }
  if (typeof x === "object") {
    // FastAPI validation shape: [{ msg, type, loc: [...] }, ...]
    if (typeof x.msg === "string") return x.msg;
    // Backend KYC_REQUIRED shape: { code, message, current_status, ... }
    if (typeof x.message === "string") return x.message;
    if (typeof x.detail === "string") return x.detail;
    if (typeof x.error === "string") return x.error;
    if (typeof x.description === "string") return x.description;
    try {
      return JSON.stringify(x);
    } catch {
      return fallback;
    }
  }
  try { return String(x); } catch { return fallback; }
}

/**
 * Extract a display-safe string from an axios/fetch error or any thrown value.
 *
 * Supported shapes:
 *   - axios error → response.data.detail (string | object | array)
 *   - axios error → response.data.message (string)
 *   - plain Error → error.message
 *   - plain string → returned as-is
 *   - object { message } → object.message
 *   - anything else → fallback
 */
export function errText(e: any, fallback = "Something went wrong"): string {
  if (!e) return fallback;

  // axios-style error
  const detail = e?.response?.data?.detail;
  const detailStr = safeStr(detail, "");
  if (detailStr) return detailStr;

  const dataMsg = safeStr(e?.response?.data?.message, "");
  if (dataMsg) return dataMsg;

  const errMsg = safeStr(e?.message, "");
  if (errMsg && errMsg !== "[object Object]") return errMsg;

  const asStr = safeStr(e, "");
  if (asStr && asStr !== "[object Object]") return asStr;

  return fallback;
}
