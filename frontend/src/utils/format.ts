export function formatINR(amount: number, opts: { compact?: boolean } = {}): string {
  if (typeof amount !== "number" || isNaN(amount)) return "₹0";
  const abs = Math.abs(amount);
  if (opts.compact && abs >= 100000) {
    if (abs >= 10000000) return `₹${(amount / 10000000).toFixed(2)}Cr`;
    return `₹${(amount / 100000).toFixed(2)}L`;
  }
  return `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(iso);
  }
}
