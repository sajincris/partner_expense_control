import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";

import Layout from "@/components/Layout";
import { ApprovalTimeline, AuditPanel, ExceptionList, VarianceTable } from "@/components/ReportPanels";
import { Amount, Card, ErrorBox, Field, KpiCard, Loading, Modal, PageHeader, Pill, StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { CostCategory, ExpenseLine, GLAccount, ReportDetail } from "@/types";
import { date, dateTime, periodLabel } from "@/utils/format";

interface LineForm {
  expense_date: string;
  cost_category_id: string;
  gl_account_id: string;
  description: string;
  amount: string;
  invoice_reference: string;
}

const EMPTY: LineForm = { expense_date: "", cost_category_id: "", gl_account_id: "", description: "", amount: "", invoice_reference: "" };

export default function ReportDetailPage() {
  const router = useRouter();
  const id = Number(router.query.id);
  const { hasRole, user } = useAuth();
  const { data: r, error, loading, reload } = useApi(() => api.get<ReportDetail>(`/expense-reports/${id}`), [id], !!id);
  const cats = useApi(() => api.get<CostCategory[]>("/master/cost-categories"), []);
  const gls = useApi(() => api.get<GLAccount[]>("/master/gl-accounts"), []);
  const [editing, setEditing] = useState<ExpenseLine | null>(null);
  const [form, setForm] = useState<LineForm | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelComment, setCancelComment] = useState("");
  const [varianceKey, setVarianceKey] = useState(0);
  const action = useAction();

  if (loading && !r) return <Layout><Loading /></Layout>;
  if (error || !r) return <Layout><ErrorBox error={error} /></Layout>;

  const isOwner = hasRole("PARTNER") && user?.partner_id === r.partner_id;
  const editable = isOwner && (r.status === "DRAFT" || r.status === "RETURNED_FOR_CLARIFICATION");
  const openExceptions = r.exceptions.filter((e) => e.status === "OPEN");
  const glFor = (catId: string) => (gls.data ?? []).filter((g) => !catId || g.cost_category_id === Number(catId));

  const openNew = () => {
    setEditing(null);
    setForm({ ...EMPTY, expense_date: `${r.fiscal_year}-${String(r.period).padStart(2, "0")}-15` });
  };
  const openEdit = (ln: ExpenseLine) => {
    setEditing(ln);
    setForm({
      expense_date: ln.expense_date, cost_category_id: String(ln.cost_category_id), gl_account_id: String(ln.gl_account_id),
      description: ln.description, amount: ln.amount, invoice_reference: ln.invoice_reference,
    });
  };
  const saveLine = async () => {
    if (!form) return;
    const body = { ...form, cost_category_id: Number(form.cost_category_id), gl_account_id: Number(form.gl_account_id), currency: r.currency };
    const ok = await action.run(() =>
      editing ? api.patch(`/expense-reports/${id}/lines/${editing.id}`, body) : api.post(`/expense-reports/${id}/lines`, body),
    );
    if (ok) {
      setForm(null);
      setVarianceKey((k) => k + 1);
      void reload();
    }
  };
  const deleteLine = async (ln: ExpenseLine) => {
    if (!window.confirm(`Delete line ${ln.line_no}? The deletion is kept in the audit trail.`)) return;
    await action.run(() => api.del(`/expense-reports/${id}/lines/${ln.id}`));
    setVarianceKey((k) => k + 1);
    void reload();
  };
  const upload = async (ln: ExpenseLine, file: File | undefined) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("line_id", String(ln.id));
    await action.run(() => api.upload(`/expense-reports/${id}/attachments`, fd));
    void reload();
  };
  const cancel = async () => {
    const ok = await action.run(() => api.post(`/expense-reports/${id}/cancel`, { comment: cancelComment }));
    if (ok) {
      setCancelOpen(false);
      void reload();
    }
  };

  return (
    <Layout>
      <PageHeader
        title={r.report_number}
        subtitle={
          <>
            {r.partner_name} · {r.project_code} {r.project_name} · {periodLabel(r.fiscal_year, r.period)} · <StatusBadge status={r.status} />
          </>
        }
        actions={
          <>
            {editable && (
              <Link href={`/reports/${id}/submit`} className="btn btn-primary">
                Review & {r.status === "RETURNED_FOR_CLARIFICATION" ? "resubmit" : "submit"} →
              </Link>
            )}
            {isOwner && r.available_actions.includes("CANCEL") && (
              <button className="btn btn-danger-ghost" onClick={() => setCancelOpen(true)}>
                Cancel report
              </button>
            )}
            {r.status === "PENDING_PM_REVIEW" && hasRole("PROJECT_MANAGER") && (
              <Link href={`/reviews/pm/${id}`} className="btn btn-primary">PM review →</Link>
            )}
            {r.status === "PENDING_FINANCE_REVIEW" && hasRole("FINANCE_OFFICER") && (
              <Link href={`/reviews/finance/${id}`} className="btn btn-primary">Finance validation →</Link>
            )}
          </>
        }
      />
      <ErrorBox error={action.error} />
      {r.status === "RETURNED_FOR_CLARIFICATION" && (
        <div className="alert alert-info">
          <strong>Returned for clarification.</strong> {r.actions.filter((a) => a.action === "RETURN").slice(-1)[0]?.comment}
        </div>
      )}

      <div className="kpis">
        <KpiCard label="Total reported" value={<Amount value={r.total_amount} ccy={r.currency} />} />
        <KpiCard label="Lines" value={r.lines.length} hint={`${r.lines.filter((l) => !l.attachments.length).length} without document`} />
        <KpiCard label="Open exceptions" value={openExceptions.length} tone={openExceptions.length ? "warn" : "good"} />
        <KpiCard label="Submissions" value={r.submission_count} hint={r.submitted_at ? `last ${dateTime(r.submitted_at)}` : "not submitted"} />
        <KpiCard label="Review due" value={r.review_due_at ? date(r.review_due_at) : "—"} tone={r.is_overdue ? "bad" : "default"} hint={r.is_overdue ? "overdue" : undefined} />
      </div>

      <Card title="Expense lines" actions={editable && <button className="btn btn-primary" onClick={openNew}>+ Add line</button>}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Date</th>
                <th>Category / GL</th>
                <th>Description</th>
                <th>Invoice</th>
                <th className="num">Amount</th>
                <th>Plan match</th>
                <th>Document</th>
                {editable && <th />}
              </tr>
            </thead>
            <tbody>
              {r.lines.map((ln) => (
                <tr key={ln.id}>
                  <td>{ln.line_no}</td>
                  <td>{date(ln.expense_date)}</td>
                  <td>{ln.cost_category_name} <span className="muted small">· {ln.gl_account_number}</span></td>
                  <td>{ln.description}</td>
                  <td className="mono small">{ln.invoice_reference}</td>
                  <td className="num"><Amount value={ln.amount} /></td>
                  <td>{r.status === "DRAFT" ? <span className="muted small">on submit</span> : ln.matched_plan_line_id ? <Pill tone="good">matched</Pill> : <Pill tone="bad">no plan</Pill>}</td>
                  <td>
                    {ln.attachments.map((a) => (
                      <button key={a.id} className="link small" onClick={() => api.download(`/expense-reports/${id}/attachments/${a.id}/download`, undefined, a.original_filename)}>
                        📎 {a.original_filename}
                      </button>
                    ))}
                    {!ln.attachments.length && <Pill tone="warn">missing</Pill>}
                    {editable && (
                      <label className="link small upload">
                        upload
                        <input type="file" accept=".pdf,.png,.jpg,.jpeg,.csv,.xlsx" onChange={(e) => upload(ln, e.target.files?.[0])} hidden />
                      </label>
                    )}
                  </td>
                  {editable && (
                    <td className="row gap nowrap">
                      <button className="btn btn-ghost small" onClick={() => openEdit(ln)}>Edit</button>
                      <button className="btn btn-ghost small text-bad" onClick={() => deleteLine(ln)}>Delete</button>
                    </td>
                  )}
                </tr>
              ))}
              {!r.lines.length && (
                <tr>
                  <td colSpan={9} className="empty">No lines yet{editable ? " — add the first expense line." : "."}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {r.lines.length > 0 && (
        <Card title="Plan vs actual for this period">
          <VarianceTable key={varianceKey} reportId={id} currency={r.currency} />
        </Card>
      )}

      <div className="grid-2">
        <Card title="Variance exceptions">
          <ExceptionList items={r.exceptions} />
        </Card>
        <Card title="Approval history">
          <ApprovalTimeline actions={r.actions} />
        </Card>
      </div>

      <AuditPanel entityType="expense_reports" entityId={id} />

      <Modal
        open={!!form}
        title={editing ? `Edit line ${editing.line_no}` : "Add expense line"}
        onClose={() => setForm(null)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setForm(null)}>Cancel</button>
            <button className="btn btn-primary" disabled={action.busy} onClick={saveLine}>Save line</button>
          </>
        }
      >
        {form && (
          <div className="form-grid two">
            <ErrorBox error={action.error} />
            <Field label="Expense date">
              <input type="date" value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} />
            </Field>
            <Field label="Invoice reference">
              <input value={form.invoice_reference} onChange={(e) => setForm({ ...form, invoice_reference: e.target.value })} maxLength={100} />
            </Field>
            <Field label="Cost category">
              <select value={form.cost_category_id} onChange={(e) => setForm({ ...form, cost_category_id: e.target.value, gl_account_id: "" })}>
                <option value="">Select…</option>
                {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="GL account">
              <select value={form.gl_account_id} onChange={(e) => setForm({ ...form, gl_account_id: e.target.value })}>
                <option value="">Select…</option>
                {glFor(form.cost_category_id).map((g) => <option key={g.id} value={g.id}>{g.account_number} — {g.name}</option>)}
              </select>
            </Field>
            <Field label={`Amount (${r.currency})`}>
              <input inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} placeholder="0.00" />
            </Field>
            <Field label="Description">
              <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={500} />
            </Field>
          </div>
        )}
      </Modal>

      <Modal
        open={cancelOpen}
        title="Cancel report"
        onClose={() => setCancelOpen(false)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setCancelOpen(false)}>Keep report</button>
            <button className="btn btn-danger" disabled={cancelComment.trim().length < 5 || action.busy} onClick={cancel}>Cancel report</button>
          </>
        }
      >
        <Field label="Reason (mandatory)">
          <textarea rows={3} value={cancelComment} onChange={(e) => setCancelComment(e.target.value)} />
        </Field>
      </Modal>
    </Layout>
  );
}
