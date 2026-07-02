import { api } from "./client";

export type KycStatus = "not_started" | "in_progress" | "submitted" | "under_review"
  | "approved" | "rejected" | "reupload_required";

export type KycProfile = {
  user_id: string;
  status: KycStatus;
  locked: boolean;
  completion: number;
  risk: "low" | "medium" | "high";
  steps: Record<string, any>;
  docs?: Record<string, any>;
  missing: string[];
  submitted_at?: string;
  approved_at?: string;
  rejected_at?: string;
  expires_at?: string;
  reject_reason?: string;
  reupload_fields?: string[];
};

export const kycApi = {
  status: () => api.get<KycProfile>("/kyc/status").then(r => r.data),
  submitStep: (step: 1|2|3|4|5|6|7, data: Record<string, any>) =>
    api.post<KycProfile>(`/kyc/step/${step}`, data).then(r => r.data),
  finalSubmit: () => api.post<KycProfile>("/kyc/submit").then(r => r.data),
  document: (docId: string) =>
    api.get(`/kyc/document/${docId}`, { responseType: "blob" }).then(r => r.data),
};

/** Convert an ImagePicker asset (with `uri`) to base64 string.
 *  ImagePicker sets base64 directly when the option is enabled — use that if present.
 */
export async function imageAssetToBase64(asset: { uri: string; base64?: string | null; mimeType?: string | null }): Promise<{ b64: string; mime: string }> {
  const mime = asset.mimeType || "image/jpeg";
  if (asset.base64) return { b64: asset.base64, mime };
  // Fallback: fetch the URI (works in RN/Expo web)
  const resp = await fetch(asset.uri);
  const blob = await resp.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read failed"));
    reader.onloadend = () => {
      const raw = String(reader.result || "");
      const b64 = raw.split(",").pop() || "";
      resolve({ b64, mime });
    };
    reader.readAsDataURL(blob);
  });
}
