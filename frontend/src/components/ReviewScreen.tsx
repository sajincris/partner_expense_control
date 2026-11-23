import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Decision, ReportDetail } from "@/types";
import { dateTime, periodLabel } from "@/utils/format";

import Layout from "./Layout";
import { ApprovalTimeline, AuditPanel, ExceptionList, VarianceTable } from "./ReportPanels";
import { Amount, Card, ErrorBox, Field, KpiCard, Loading, PageHeader, StatusBadge } from "./ui";

const COPY = {
  PM: {
    title: "Project Manager review",
    question: "Is the variance justified by a real project need, and was the activity implemented?",
    expected: "PENDING_PM_REVIEW",
    endpoint: "pm-review",
    approve: "Approve → send to Finance",
  },
  FINANCE: {
    title: "Finance validation",
    question: "Is budget available, is the accounting treatment correct and are documents sufficient? Finance is the final approver.",
    expected: "PENDING_FINANCE_REVIEW",
    endpoint: "finance-review",
    approve: "Final approval",
  },
} as const;

export default function ReviewScreen({ stage }: { stage: "PM" | "FINANCE" }) {
  const router = useRouter();
  const id = Number(router.query.id);
  const { user } = useAuth();
  const cfg = COPY[stage];
  const { data: r, error, loading, reload } = useApi(() => api.get<ReportDetail>(`/expense-reports/${id}`), [id], !!id);
  const [comment, setComment] = useState("");
  const [checklist, setChecklist] = useState({ budget_available: false, accounting_treatment_ok: false, documents_ok: false });
  const { busy, error: actionError, run } = useAction();

  if (loading && !r) return <Layout><Loading /></Layout>;
  if (!r) return <Layout><ErrorBox error={error} /></Layout>;

  const actionable = r.status === cfg.expected;
  const allChecked = Object.values(checklist).every(Boolean);
  const pmStep = r.actions.filter((a) => a.stage === "PM").slice(-1)[0];

  const decide = async (decision: Decision) => {
    const body = { decision, comment, ...(stage === "FINANCE" ? { checklist } : {}) };
    const res = await run(() => api.post<ReportDetail>(`/expense-reports/${id}/${cfg.endpoint}`, body));
    if (res) {
      void reload();
      void router.push("/exceptions");
    }
  };

  return (
    <Layout roles={[stage === "PM" ? "PROJECT_MANAGER" : "FINANCE_OFFICER"]}>
      <PageHeader
        title={`${cfg.title} · ${r.report_number}`}
        subtitle={<>{r.partner_name} · {r.project_code} · {periodLabel(r.fiscal_year, r.period)} · <StatusBadge status={r.status} /></>}
        actions={<Link href={`/reports/${id}`} className="btn btn-ghost">Open full report</Link>}
      />
      {!actionable && <div className="alert alert-info">This report is not waiting for a {stage === "PM" ? "PM review" : "Finance validation"}; the screen is read-only.</div>}

      <div className="kpis">
        <KpiCard label="Reported" value={<Amount value={r.total_amount} ccy={r.currency} />} />
        <KpiCard label="Open exceptions" value={r.exceptions.filter((e) => e.status === "OPEN").length} tone="warn" />
        <KpiCard label="Submitted" value={dateTime(r.submitted_at)} hint={`submission #${r.submission_count}`} />
        <KpiCard label="Due" value={dateTime(r.review_due_at)} tone={r.is_overdue ? "bad" : "default"} hint={r.is_overdue ? "overdue" : "within SLA"} />
      </div>

      <div className="review-layout">
        <div>
          <Card title="Variance exceptions">
            <ExceptionList items={r.exceptions.filter((e) => e.status !== "SUPERSEDED")} />
          </Card>
          <Card title="Plan vs actual">
            <VarianceTable reportId={id} currency={r.currency} />
          </Card>
          {r.partner_comment && (
            <Card title="Partner comment">
              <p>{r.partner_comment}</p>
            </Card>
          )}
          <Card title="Approval history">
            <ApprovalTimeline actions={r.actions} />
          </Card>
          <AuditPanel entityType="expense_reports" entityId={id} />
        </div>

        <aside className="decision-panel">
          <Card title="Decision">
            <p className="small muted">{cfg.question}</p>
            {stage === "FINANCE" && pmStep && (
              <div className="note">
                <strong>PM justification ({pmStep.actor_name}):</strong> {pmStep.comment}
              </div>
            )}
            <ErrorBox error={actionError} />
            {stage === "FINANCE" && (
              <div className="checklist">
                {(
                  [
                    ["budget_available", "Budget is available in the annual envelope"],
                    ["accounting_treatment_ok", "Accounting treatment / GL coding is correct"],
                    ["documents_ok", "Supporting documents are complete and valid"],
                  ] as const
                ).map(([k, label]) => (
                  <label key={k} className="checkbox">
                    <input type="checkbox" checked={checklist[k]} disabled={!actionable} onChange={(e) => setChecklist({ ...checklist, [k]: e.target.checked })} />
                    {label}
                  </label>
                ))}
              </div>
            )}
            <Field label="Comment (mandatory for every decision)">
              <textarea rows={5} value={comment} disabled={!actionable} onChange={(e) => setComment(e.target.value)} maxLength={4000} />
            </Field>
            <div className="decision-buttons">
              <button className="btn btn-success" disabled={!actionable || busy || comment.trim().length < 5 || (stage === "FINANCE" && !allChecked)} onClick={() => decide("APPROVE")}>
                ✓ {cfg.approve}
              </button>
              <button className="btn btn-warn" disabled={!actionable || busy || comment.trim().length < 5} onClick={() => decide("RETURN")}>
                ↩ Return for clarification
              </button>
              <button className="btn btn-danger" disabled={!actionable || busy || comment.trim().length < 5} onClick={() => decide("REJECT")}>
                ✕ Reject
              </button>
            </div>
            <p className="small muted">
              Signed as <strong>{user?.full_name}</strong>. Your decision, comment and checklist are written to the immutable approval journal.
            </p>
          </Card>
        </aside>
      </div>
    </Layout>
  );
}
