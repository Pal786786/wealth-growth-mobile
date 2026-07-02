/**
 * Global KYC gate: whenever ANY API returns 403 with code="KYC_REQUIRED",
 * we broadcast an event so the mounted <KycRequiredModal /> pops up.
 *
 * Wire once in /app/frontend/src/api/client.ts:
 *   import { installKycInterceptor } from "./kycGate";
 *   installKycInterceptor(api);
 */
import type { AxiosInstance, AxiosError } from "axios";
import { DeviceEventEmitter } from "react-native";

export const KYC_REQUIRED_EVENT = "mfb:kyc-required";

export type KycRequiredPayload = {
  code: "KYC_REQUIRED";
  message: string;
  current_status: string;
  action_url: string;
};

export function emitKycRequired(payload: KycRequiredPayload) {
  DeviceEventEmitter.emit(KYC_REQUIRED_EVENT, payload);
}

export function installKycInterceptor(instance: AxiosInstance) {
  instance.interceptors.response.use(
    r => r,
    (err: AxiosError<any>) => {
      const status = err.response?.status;
      const raw = err.response?.data && typeof err.response.data === "object"
        ? (err.response.data as any).detail
        : null;
      const isKycObject = raw && typeof raw === "object" && raw.code === "KYC_REQUIRED";
      if (status === 403 && isKycObject) {
        emitKycRequired(raw as KycRequiredPayload);
      }

      // CRITICAL: FastAPI returns `detail` as either a string, a validation
      // array, or a structured object (e.g. KYC_REQUIRED). Screens across the
      // app do `show("error", e?.response?.data?.detail || "...")` which used
      // to pass the raw object into <Text> and crash React with
      //   "Objects are not valid as a React child".
      // Normalize `detail` to a plain string here so every downstream catch
      // handler receives a safe value. We keep the original object under
      // `detailRaw` in case any advanced screen needs the structured payload.
      try {
        const data: any = err.response?.data;
        if (data && typeof data === "object" && "detail" in data) {
          const d = data.detail;
          if (d !== null && typeof d === "object") {
            data.detailRaw = d;
            if (typeof d.message === "string") data.detail = d.message;
            else if (typeof d.msg === "string") data.detail = d.msg;
            else if (Array.isArray(d)) {
              // FastAPI validation array [{msg,type,loc}, ...]
              data.detail = d.map((x: any) => x?.msg || "invalid").join("; ") || "Validation error";
            } else {
              try { data.detail = JSON.stringify(d); } catch { data.detail = "Request failed"; }
            }
          }
        }
      } catch { /* never let normalization itself throw */ }

      return Promise.reject(err);
    },
  );
}
