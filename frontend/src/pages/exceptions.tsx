import Link from "next/link";
import { useState } from "react";

import Layout from "@/components/Layout";
import { Amount, Card, Empty, ErrorBox, Loading, PageHeader, Pagination, Pill, SeverityBadge, StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Page, QueueItem } from "@/types";
import { dateTime, EXCEPTION_LABEL, pct, periodLabel } from "@/utils/format";

type Stage = "" | "PM" | "FINANCE";

export default function ExceptionQueue() {
  const { hasRole } = useAuth();
  const defaultStage: Stage = hasRole("FINANCE_OFFICER") ? "FINANCE" : hasRole("PROJECT_MANAGER") ? "PM" : "";
  const [stage, setStage] = useState<Stage>(defaultStage);
  const [overdue, setOverdue] = useState(false);
  const [page, setPage] = useState(1);
  const { data, error, loading } = useApi(
    () => api.get<Page<QueueItem>>("/reviews/queue", { stage: stage || undefined, overdue: overdue || undefined, page, size: 20 }),
    [stage, overdue, page],
  );

  const reviewLink = (q: QueueItem) => (q.stage === "PM" ? `/reviews/pm/${q.id}` : `/reviews/finance/${q.id}`);
  const canAct = (q: QueueItem) => (q.stage === "PM" ? hasRole("PROJECT_MANAGER") : hasRole("FINANCE_OFFICER"));

  return (
    <Layout roles={["PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"]}>
      <PageHeader title="Variance exception queue" subtitle="Reports outside tolerance awaiting PM justification or Finance validation" />
      <div className="tabs">
        {([["", "All pending"], ["PM", "Pending PM review"], ["FINANCE", "Pending Finance validation"]] as [Stage, string][]).map(([k, label]) => (
          <button key={k} className={`tab ${stage === k ? "active" : ""}`} onClick={() => { setStage(k); setPage(1); }}>
            {label}
          </button>
        ))}
        <label className="checkbox inline">
          <input type="checkbox" checked={overdue} onChange={(e) => { setOverdue(e.target.checked); setPage(1); }} /> Overdue only
        </label>
      </div>
      <Card>
        <ErrorBox error={error} />
        {loading && !data && <Loading />}
        {data && data.items.length === 0 && <Empty>The queue is empty. 🎉</Empty>}
        {data && data.items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Partner / project</th>
                  <th>Period</th>
                  <th className="num">Amount</th>
                  <th>Exceptions</th>
                  <th>Severity</th>
                  <th className="num">Max var.</th>
                  <th>Stage</th>
                  <th>Due</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((q) => (
                  <tr key={q.id} className={q.is_overdue ? "row-overdue" : ""}>
                    <td><Link href={`/reports/${q.id}`}>{q.report_number}</Link></td>
                    <td>{q.partner_name} <span className="muted small">· {q.project_code}</span></td>
                    <td>{periodLabel(q.fiscal_year, q.period)}</td>
                    <td className="num"><Amount value={q.total_amount} /></td>
                    <td>
                      {q.exception_types.map((t) => (
                        <Pill key={t} tone="warn">{EXCEPTION_LABEL[t]}</Pill>
                      ))}
                    </td>
                    <td><SeverityBadge severity={q.highest_severity} /></td>
                    <td className="num">{pct(q.max_variance_pct)}</td>
                    <td><StatusBadge status={q.status} /></td>
                    <td className="small">
                      <span className={q.is_overdue ? "text-bad" : ""}>{dateTime(q.review_due_at)}</span>
                      {q.is_overdue && <Pill tone="bad">overdue</Pill>}
                    </td>
                    <td>
                      {canAct(q) ? (
                        <Link href={reviewLink(q)} className="btn btn-primary small">Review</Link>
                      ) : (
                        <Link href={`/reports/${q.id}`} className="btn btn-ghost small">View</Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Card>
    </Layout>
  );
}
