import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import type { Withdrawal } from "@/src/api/withdrawal";

const STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting OTP",
  under_review: "Under Review",
  approved: "Approved",
  processing: "Processing",
  completed: "Completed",
  rejected: "Rejected",
  failed: "Failed",
  cancelled: "Cancelled",
};

function fmtDate(iso?: string) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function inr(n: number) {
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function buildReceiptHTML(w: Withdrawal, user?: { full_name?: string; email?: string; mobile?: string }): string {
  const timeline: { at?: string; label: string }[] = [
    { at: w.created_at, label: "Requested" },
    { at: w.verified_at, label: "OTP verified" },
    { at: w.approved_at, label: "Approved" },
    { at: w.processing_at, label: "Processing" },
    { at: w.completed_at, label: "Completed" },
    { at: w.rejected_at, label: `Rejected${w.reason_admin ? ": " + w.reason_admin : ""}` },
    { at: w.failed_at, label: `Failed${w.reason_admin ? ": " + w.reason_admin : ""}` },
  ].filter((x) => !!x.at);

  return `
<!doctype html><html><head><meta charset="utf-8" />
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #0F172A; margin: 0; padding: 24px; background: #F8FAFC; }
  .card { background: #fff; border-radius: 20px; overflow: hidden; box-shadow: 0 6px 24px rgba(15,23,42,0.08); }
  .hero { background: linear-gradient(135deg, #0EA5E9 0%, #0F172A 100%); color: #fff; padding: 28px 24px; }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 900; letter-spacing: 0.5px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: #F59E0B; box-shadow: 0 0 12px #F59E0B; }
  .amount { font-size: 44px; font-weight: 900; letter-spacing: -1px; margin-top: 12px; }
  .sub { font-size: 12px; opacity: 0.85; margin-top: 6px; letter-spacing: 0.5px; text-transform: uppercase; }
  .status { display: inline-block; padding: 4px 12px; border-radius: 999px; font-weight: 800; font-size: 11px; letter-spacing: 1px; background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.35); text-transform: uppercase; margin-top: 10px; }
  .body { padding: 24px; }
  .row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px dashed #E2E8F0; font-size: 13px; }
  .row:last-child { border-bottom: none; }
  .label { color: #64748B; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; font-size: 11px; }
  .value { color: #0F172A; font-weight: 700; text-align: right; }
  .timeline { margin-top: 16px; padding: 16px; background: #F8FAFC; border-radius: 14px; }
  .step { padding: 8px 0; font-size: 12px; border-left: 3px solid #38BDF8; padding-left: 10px; margin-bottom: 4px; }
  .footer { padding: 20px 24px; background: #0F172A; color: #94A3B8; font-size: 10px; text-align: center; letter-spacing: 0.5px; }
  .footer b { color: #F59E0B; }
</style></head><body>
  <div class="card">
    <div class="hero">
      <div class="brand"><span class="dot"></span> MY FUNDING BANK</div>
      <div class="sub">Withdrawal Receipt</div>
      <div class="amount">${inr(w.amount)}</div>
      <div class="sub">Ref · ${w.reference_no}</div>
      <span class="status">${STATUS_LABEL[w.status] || w.status}</span>
    </div>
    <div class="body">
      <div class="row"><span class="label">Account holder</span><span class="value">${w.bank_snapshot.holder_name}</span></div>
      <div class="row"><span class="label">Bank</span><span class="value">${w.bank_snapshot.bank_name}</span></div>
      <div class="row"><span class="label">Account</span><span class="value">${w.bank_snapshot.account_masked}</span></div>
      <div class="row"><span class="label">IFSC</span><span class="value">${w.bank_snapshot.ifsc}</span></div>
      <div class="row"><span class="label">Charge</span><span class="value">${inr(w.charge || 0)}</span></div>
      <div class="row"><span class="label">Net credit</span><span class="value">${inr(w.net_amount)}</span></div>
      <div class="row"><span class="label">Requested at</span><span class="value">${fmtDate(w.created_at)}</span></div>
      ${user?.full_name ? `<div class="row"><span class="label">User</span><span class="value">${user.full_name}</span></div>` : ""}
      ${user?.mobile ? `<div class="row"><span class="label">Mobile</span><span class="value">${user.mobile}</span></div>` : ""}

      <div class="timeline">
        <div class="label" style="margin-bottom: 6px;">Status timeline</div>
        ${timeline.map((t) => `<div class="step"><b>${t.label}</b><br/><span style="color:#64748B">${fmtDate(t.at)}</span></div>`).join("")}
      </div>
    </div>
    <div class="footer">
      This is a system-generated receipt. Save it for your records. · <b>myfundingbank.in</b>
    </div>
  </div>
</body></html>`;
}

export async function generateAndShareReceipt(w: Withdrawal, user?: { full_name?: string; email?: string; mobile?: string }): Promise<{ uri: string }> {
  const html = buildReceiptHTML(w, user);
  const { uri } = await Print.printToFileAsync({ html, base64: false });
  try {
    if (await Sharing.isAvailableAsync()) {
      await Sharing.shareAsync(uri, {
        UTI: "com.adobe.pdf", mimeType: "application/pdf",
        dialogTitle: `MFB Withdrawal · ${w.reference_no}`,
      });
    }
  } catch { /* silent */ }
  return { uri };
}
