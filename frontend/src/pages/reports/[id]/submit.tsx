import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";

import Layout from "@/components/Layout";
import { VarianceTable } from "@/components/ReportPanels";
import { Amount, Card, ErrorBox, Field, Loading, PageHeader, Pill, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { ReportDetail, VarianceResult } from "@/types";
import { EXCEPTION_LABEL, periodLabel } from "@/utils/format";

export default function SubmitReport() {
  const router = useRouter();
  const id = Number(router.query.id);
  const report = useApi(() => api.get<ReportDetail>(`/expense-reports/${id}`), [id], !!id);
  const preview = useApi(() => api.get<VarianceResult>(`/expense-reports/${id}/variance`), [id], !!id);
  const [comment, setComment] = useState("");
  const [confirm, setConfirm] = useState(false);
  const { busy, error, run } = useAction();

  const r = report.data;
  if (!r) return <Layout roles={["PARTNER"]}>{report.error ? <ErrorBox error={report.error} /> : <Loading />}</Layout>;
  const resubmit = r.status === "RETURNED_FOR_CLARIFICATION";
  const missingDocs = r.lines.filter((l) => !l.attachments.length).length;

  const submit = async () => {
    const res = await run(() => api.post<ReportDetail>(`/expense-reports/${id}/submit`, { comment: comment || null }));
    if (res) void router.push(`/reports/${id}`);
  };

  return (
    <Layout roles={["PARTNER"]}>
      <PageHeader
        title={`${resubmit ? "Resubmit" : "Submit"} ${r.report_number}`}
        subtitle={<>{r.project_code} · {periodLabel(r.fiscal_year, r.period)} · <StatusBadge status={r.status} /></>}
        actions={<Link href={`/reports/${id}`} className="btn btn-ghost">← Back to lines</Link>}
      />
      <div className="steps">
        <span className="step done">1 · Header</span>
        <span className="step done">2 · Lines & documents</span>
        <span className="step active">3 · Review & submit</span>
      </div>

      <Card title="Pre-submission check (live calculation)">
        <VarianceTable reportId={id} currency={r.currency} />
      </Card>

      <Card title="What will happen">
        {preview.loading && <Loading />}
        <ErrorBox error={preview.error} />
        {preview.data &&
          (preview.data.auto_accept ? (
            <div className="alert alert-good">
              All lines are within tolerance and no control exception was found. The report will be <strong>automatically accepted</strong>.
            </div>
          ) : (
            <div className="alert alert-warn">
              <strong>{preview.data.findings.length} exception(s)</strong> will be raised and the report routed to the Project Manager, then Finance:
              <ul>
                {preview.data.findings.map((f, i) => (
                  <li key={i}>
                    <Pill tone="warn">{EXCEPTION_LABEL[f.exception_type]}</Pill> {f.message}
                  </li>
                ))}
              </ul>
              Add a justification below to speed up the review.
            </div>
          ))}
        <div className="row gap wrap small">
          <span>Lines: <strong>{r.lines.length}</strong></span>
          <span>Total: <strong><Amount value={r.total_amount} ccy={r.currency} /></strong></span>
          <span>Lines without document: <strong className={missingDocs ? "text-bad" : ""}>{missingDocs}</strong></span>
        </div>
      </Card>

      <Card title={resubmit ? "Clarification (mandatory)" : "Comment / justification"}>
        <ErrorBox error={error} />
        <Field label={resubmit ? "Explain what you changed or clarified" : "Optional note for reviewers"}>
          <textarea rows={4} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={4000} />
        </Field>
        <label className="checkbox">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />I confirm the expenses are real, eligible, supported by the attached documents and not reported elsewhere.
        </label>
        <div className="row gap">
          <button className="btn btn-primary" disabled={!confirm || busy || (resubmit && comment.trim().length < 5) || !r.lines.length} onClick={submit}>
            {busy ? "Submitting…" : resubmit ? "Resubmit report" : "Submit report"}
          </button>
        </div>
      </Card>
    </Layout>
  );
}
