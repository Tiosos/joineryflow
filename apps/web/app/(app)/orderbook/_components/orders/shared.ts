export const STATUSES = [
  "Draft", "Pending", "Approved", "Rejected",
  "Delivered", "Cancelled", "Hold", "Quote", "Next",
] as const;

export const PRIORITIES = ["High", "Medium", "Low", "Next", "Hold", "Quote"] as const;

export function statusClasses(status: string): string {
  switch (status) {
    case "Approved":
    case "Delivered": return "bg-[#e4efe5] text-[#3f7d48]";
    case "Rejected":
    case "Cancelled": return "bg-[#f2dcd9] text-[#b4443d]";
    case "Hold":
    case "Pending":   return "bg-[#f4ebd9] text-[#c48a2e]";
    case "Quote":
    case "Next":      return "bg-[#f3e0d6] text-[#a84f31]";
    default:          return "bg-[#f4f2ed] text-[#8f8b80]";
  }
}

/** Decimal arrives as a string (see `orders-types.ts`), so parse before formatting. */
export function money(v: string | null, currency: string | null): string {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `${currency ? `${currency} ` : "$"}${n.toFixed(2)}`;
}

/** Trims Decimal's trailing zeros: "1.000" reads as "1". */
export function qty(v: string | null): string | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isNaN(n) ? v : String(n);
}

export type ErrorDetail = { code?: string; status?: string };

export function orderLocked(body: unknown): ErrorDetail | null {
  const d = (body as { detail?: ErrorDetail } | null)?.detail;
  return d?.code === "ORDER_LOCKED" ? d : null;
}

export function lockedMessage(d: ErrorDetail): string {
  return `Order is ${d.status ?? "locked"} — change its status to edit`;
}

export function fieldErrorMessage(res: Response, body: unknown, field: string): string {
  const locked = orderLocked(body);
  if (locked) return lockedMessage(locked);
  const code = (body as { detail?: { code?: string; conflicts?: Record<string, { current_value?: unknown }> } } | null)
    ?.detail?.code;
  if (code === "FIELD_CONFLICT") {
    const cur = (body as { detail?: { conflicts?: Record<string, { current_value?: unknown }> } })
      ?.detail?.conflicts?.[field]?.current_value;
    return `Changed to "${cur ?? "…"}" by someone else — reload to see it`;
  }
  // `patch_order_route`'s 404 is a plain string detail ("order not found"),
  // not a {code} object, matching every other 404 in this module — so it's
  // the HTTP status, not a code, that identifies it here.
  if (res.status === 404) return "Order not found";
  if (code === "APPROVAL_ROUTE_REQUIRED") return "This order needs approval — use the Approval section below";
  if (code === "COST_CENTER_LOCKED") return "A budget commitment is already posted against this cost centre, so it cannot be changed";
  if (code === "COST_CENTER_NOT_FOUND") return "That cost centre is not available";
  if (code === "APPROVAL_FLAG_FORBIDDEN") return "Only a manager or admin can flag an order for approval";
  return `Save failed (${res.status})`;
}

const APPROVAL_MESSAGES: Record<string, string> = {
  NOT_REQUIRED: "This order does not need approval",
  NOT_REQUESTABLE: "Only a Draft or Rejected order can be sent for approval",
  NOT_PENDING: "This order is no longer waiting for approval — reload",
  SELF_APPROVAL: "You requested this order, so someone else must approve it",
  NOTE_REQUIRED: "Say why in the note to reject",
};

export function approvalErrorMessage(res: Response, body: unknown): string {
  const code = (body as { detail?: { code?: string } } | null)?.detail?.code;
  if (code && APPROVAL_MESSAGES[code]) return APPROVAL_MESSAGES[code];
  if (res.status === 403) return "You are not allowed to do that";
  return `Failed (${res.status})`;
}
