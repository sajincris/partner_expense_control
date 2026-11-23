import { ReactNode, useEffect } from "react";

import { ApiError } from "@/services/api";
import type { ReportStatus, Severity } from "@/types";
import { STATUS_LABEL } from "@/utils/format";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="row gap">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, className = "" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          <h2>{title}</h2>
          {actions}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function KpiCard({ label, value, hint, tone = "default" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "warn" | "bad" }) {
  return (
    <div className={`kpi kpi-${tone}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}

const STATUS_TONE: Record<ReportStatus, string> = {
  DRAFT: "neutral",
  SUBMITTED: "info",
  AUTO_ACCEPTED: "good",
  PENDING_PM_REVIEW: "warn",
  PENDING_FINANCE_REVIEW: "warn",
  RETURNED_FOR_CLARIFICATION: "info",
  APPROVED: "good",
  REJECTED: "bad",
  CANCELLED: "neutral",
};

export function StatusBadge({ status }: { status: ReportStatus }) {
  return <span className={`badge badge-${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}

export function SeverityBadge({ severity }: { severity: Severity | null }) {
  if (!severity) return <span className="muted">—</span>;
  const tone = severity === "HIGH" ? "bad" : severity === "MEDIUM" ? "warn" : "neutral";
  return <span className={`badge badge-${tone}`}>{severity}</span>;
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function ErrorBox({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <div className="alert alert-bad" role="alert">
      <strong>{error.message}</strong>
      {error.lines.length > 0 && (
        <ul>
          {error.lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      )}
      <span className="muted small"> [{error.code}]</span>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="loading">{label}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Pagination({ page, pages, total, onPage }: { page: number; pages: number; total: number; onPage: (p: number) => void }) {
  if (pages <= 1) return <div className="pagination muted small">{total} record(s)</div>;
  return (
    <div className="pagination">
      <span className="muted small">{total} record(s)</span>
      <button className="btn btn-ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ‹ Prev
      </button>
      <span className="small">
        Page {page} of {pages}
      </span>
      <button className="btn btn-ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next ›
      </button>
    </div>
  );
}

export function Modal({ open, title, onClose, children, footer, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h3>{title}</h3>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Amount({ value, ccy, colored }: { value: string | null | undefined; ccy?: string; colored?: boolean }) {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  const n = Number(value);
  const cls = colored ? (n > 0 ? "amount over" : n < 0 ? "amount under" : "amount") : "amount";
  const text = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
  return (
    <span className={cls}>
      {ccy ? `${ccy} ` : ""}
      {colored && n > 0 ? "+" : ""}
      {text}
    </span>
  );
}
