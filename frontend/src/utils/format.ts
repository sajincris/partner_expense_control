import type { ExceptionType, ReportStatus } from "@/types";

const moneyFmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const money = (v: string | number | null | undefined, ccy?: string) =>
  v === null || v === undefined || v === "" ? "—" : `${ccy ? ccy + " " : ""}${moneyFmt.format(Number(v))}`;

export const compact = (v: string | number | null | undefined) => (v === null || v === undefined ? "—" : compactFmt.format(Number(v)));

export const pct = (v: string | number | null | undefined) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}%`);

export const date = (v: string | null | undefined) => (v ? new Date(v).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—");

export const dateTime = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const periodLabel = (fy: number, p: number) => `${MONTHS[p - 1]} ${fy}`;

export const STATUS_LABEL: Record<ReportStatus, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  AUTO_ACCEPTED: "Auto-accepted",
  PENDING_PM_REVIEW: "Pending PM review",
  PENDING_FINANCE_REVIEW: "Pending Finance",
  RETURNED_FOR_CLARIFICATION: "Returned",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

export const EXCEPTION_LABEL: Record<ExceptionType, string> = {
  VARIANCE_OVER_TOLERANCE: "Variance over tolerance",
  NO_PLAN_LINE: "No plan line",
  DUPLICATE_INVOICE: "Duplicate invoice",
  MISSING_DOCUMENT: "Missing document",
  OVER_ANNUAL_BUDGET: "Over annual budget",
};

export const sign = (v: string | number | null | undefined) => (v === null || v === undefined ? 0 : Math.sign(Number(v)));
