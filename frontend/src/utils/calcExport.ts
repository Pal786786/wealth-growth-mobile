/**
 * Investment Calculator — PDF/Share helpers.
 * Pure functions producing HTML or text from a calc result snapshot.
 */
import { Platform, Share } from "react-native";
import { formatINR } from "./format";

export type CalcSnapshot = {
  name?: string;
  calc_type: "onetime" | "sip" | "daily" | "compound";
  amount: number;
  duration: number;
  rate_pct: number;
  reinvest: boolean;
  invested: number;
  profit: number;
  maturity: number;
  growth: number;
  created_at?: string;
};

const TYPE_LABEL: Record<string, string> = {
  onetime: "One-Time Investment",
  sip: "SIP (Monthly)",
  daily: "Daily Profit",
  compound: "Compound Growth",
};

const DURATION_LABEL: Record<string, string> = {
  onetime: "months",
  sip: "months",
  daily: "days",
  compound: "years",
};

const RATE_LABEL: Record<string, string> = {
  onetime: "Return %",
  sip: "Annual Return %",
  daily: "Daily Return %",
  compound: "Annual Return %",
};

export function calcPlanText(s: CalcSnapshot): string {
  const lines = [
    `📊 My Funding Bank — Investment Plan`,
    s.name ? `Plan: ${s.name}` : null,
    ``,
    `Type: ${TYPE_LABEL[s.calc_type] || s.calc_type}`,
    `Investment: ${formatINR(s.amount)}${s.calc_type === "sip" ? " / month" : ""}`,
    `Duration: ${s.duration} ${DURATION_LABEL[s.calc_type]}`,
    `${RATE_LABEL[s.calc_type]}: ${s.rate_pct}%`,
    s.calc_type === "onetime" || s.calc_type === "daily" ? `Reinvest Profit: ${s.reinvest ? "Yes" : "No"}` : null,
    ``,
    `Total Invested: ${formatINR(s.invested)}`,
    `Estimated Profit: ${formatINR(s.profit)}`,
    `Maturity Value: ${formatINR(s.maturity)}`,
    `Growth: ${s.growth.toFixed(2)}%`,
    ``,
    `Calculated on My Funding Bank app.`,
    `Estimates only — actual returns may vary.`,
  ].filter(Boolean) as string[];
  return lines.join("\n");
}

export function calcPlanHTML(s: CalcSnapshot): string {
  const created = s.created_at ? new Date(s.created_at).toLocaleString("en-IN") : new Date().toLocaleString("en-IN");
  const reinvestRow = (s.calc_type === "onetime" || s.calc_type === "daily")
    ? `<tr><td>Reinvest Profit</td><td><b>${s.reinvest ? "Enabled" : "Disabled"}</b></td></tr>` : "";
  return `<!doctype html>
<html><head><meta charset="utf-8" />
<title>${escapeHtml(s.name || "Investment Plan")}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 32px; color: #0F172A; background: #fff; }
  .header { display: flex; align-items: center; gap: 12px; padding-bottom: 16px; border-bottom: 2px solid #0EA5E9; margin-bottom: 24px; }
  .logo { width: 48px; height: 48px; border-radius: 14px; background: linear-gradient(135deg, #0EA5E9, #2563EB); display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 22px; }
  .brand { font-size: 22px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px; }
  .brand small { display:block; font-size: 11px; color: #64748B; font-weight: 600; letter-spacing: 1.5px; }
  h1 { font-size: 18px; margin: 0 0 4px; color: #0F172A; }
  .meta { color: #64748B; font-size: 12px; margin-bottom: 24px; }
  .hero { background: linear-gradient(135deg, #0EA5E9, #2563EB); color: #fff; padding: 24px; border-radius: 20px; margin: 16px 0 24px; }
  .hero .label { font-size: 11px; letter-spacing: 1.3px; font-weight: 700; opacity: 0.85; }
  .hero .value { font-size: 36px; font-weight: 800; margin-top: 4px; letter-spacing: -0.6px; }
  .hero .row { display: flex; gap: 20px; margin-top: 16px; }
  .hero .stat { flex: 1; }
  .hero .stat .l { font-size: 10px; letter-spacing: 1px; opacity: 0.85; font-weight: 700; }
  .hero .stat .v { font-size: 18px; font-weight: 800; margin-top: 2px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  td { padding: 10px 0; border-bottom: 1px dashed #E2E8F0; font-size: 13px; }
  td:first-child { color: #64748B; }
  td:last-child { text-align: right; }
  .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #E2E8F0; font-size: 10px; color: #94A3B8; line-height: 1.6; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; background: #DCFCE7; color: #166534; font-size: 11px; font-weight: 700; margin-left: 8px; }
</style></head>
<body>
  <div class="header">
    <div class="logo">MFB</div>
    <div class="brand">My Funding Bank<small>INVESTMENT PLAN · CALCULATOR</small></div>
  </div>
  <h1>${escapeHtml(s.name || "Untitled Plan")}<span class="badge">${escapeHtml(TYPE_LABEL[s.calc_type] || s.calc_type)}</span></h1>
  <div class="meta">Generated on ${escapeHtml(created)}</div>

  <div class="hero">
    <div class="label">MATURITY VALUE</div>
    <div class="value">${escapeHtml(formatINR(s.maturity))}</div>
    <div class="row">
      <div class="stat"><div class="l">INVESTED</div><div class="v">${escapeHtml(formatINR(s.invested))}</div></div>
      <div class="stat"><div class="l">PROFIT</div><div class="v">${escapeHtml(formatINR(s.profit))}</div></div>
      <div class="stat"><div class="l">GROWTH</div><div class="v">${s.growth.toFixed(2)}%</div></div>
    </div>
  </div>

  <h2 style="font-size:14px; margin:0 0 6px; color:#0F172A;">Plan Details</h2>
  <table>
    <tr><td>Investment Type</td><td><b>${escapeHtml(TYPE_LABEL[s.calc_type] || s.calc_type)}</b></td></tr>
    <tr><td>${s.calc_type === "sip" ? "Monthly Amount" : "Investment Amount"}</td><td><b>${escapeHtml(formatINR(s.amount))}</b></td></tr>
    <tr><td>Duration</td><td><b>${s.duration} ${escapeHtml(DURATION_LABEL[s.calc_type])}</b></td></tr>
    <tr><td>${escapeHtml(RATE_LABEL[s.calc_type])}</td><td><b>${s.rate_pct}%</b></td></tr>
    ${reinvestRow}
  </table>

  <div class="footer">
    Disclaimer: This is an investment estimate based on the inputs provided. Actual returns may vary based on market conditions, fees, taxes, and other factors. My Funding Bank does not guarantee any specific return.
  </div>
</body></html>`;
}

function escapeHtml(s: string): string {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

export async function shareCalcText(s: CalcSnapshot): Promise<void> {
  const msg = calcPlanText(s);
  await Share.share(
    Platform.OS === "ios"
      ? { message: msg }
      : { message: msg, title: s.name || "Investment Plan" },
  );
}
