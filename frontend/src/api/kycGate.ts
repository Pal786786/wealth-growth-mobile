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
      const detail: any = err.response?.data && typeof err.response.data === "object"
        ? (err.response.data as any).detail
        : null;
      if (status === 403 && detail && detail.code === "KYC_REQUIRED") {
        emitKycRequired(detail as KycRequiredPayload);
      }
      return Promise.reject(err);
    },
  );
}
