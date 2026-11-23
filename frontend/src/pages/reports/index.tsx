import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import Layout from "@/components/Layout";
import { Amount, Card, ErrorBox, Loading, PageHeader, Pagination, Pill, StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Page, Project, ReportStatus, ReportSummary } from "@/types";
import { dateTime, MONTHS, periodLabel, STATUS_LABEL } from "@/utils/format";

const STATUSES = Object.keys(STATUS_LABEL) as ReportStatus[];

export default function Reports() {
  const router = useRouter();
  const { hasRole } = useAuth();
  const [status, setStatus] = useState<string>("");
  const [projectId, setProjectId] = useState<string>("");
  const [period, setPeriod] = useState<string>("");
  const [fy, setFy] = useState<string>("2026");
  const [sort, setSort] = useState("-created_at");
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (typeof router.query.status === "string") setStatus(router.query.status);
  }, [router.query.status]);

  const projects = useApi(() => api.get<Page<Project>>("/projects", { size: 100 }), []);
  const { data, error, loading } = useApi(
    () => api.get<Page<ReportSummary>>("/expense-reports", { status: status || undefined, project_id: projectId, period, fiscal_year: fy, sort, page, size: 20 }),
    [status, projectId, period, fy, sort, page],
  );

  const reset = () => setPage(1);

  return (
    <Layout>
      <PageHeader
        title="Expense reports"
        subtitle="Monthly partner expense reports and their control status"
        actions={
          <>
            <button className="btn btn-ghost" onClick={() => api.download("/reports/expense-reports/export", { fiscal_year: fy, format: "xlsx" })}>
              ⇩ Excel
            </button>
            {hasRole("PARTNER") && (
              <Link href="/reports/new" className="btn btn-primary">
                + New report
              </Link>
            )}
          </>
        }
      />
      <Card>
        <div className="filters">
          <select value={fy} onChange={(e) => { setFy(e.target.value); reset(); }} aria-label="Fiscal year">
            <option value="">All years</option>
            {[2025, 2026, 2027].map((y) => <option key={y}>{y}</option>)}
          </select>
          <select value={status} onChange={(e) => { setStatus(e.target.value); reset(); }} aria-label="Status">
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
          <select value={projectId} onChange={(e) => { setProjectId(e.target.value); reset(); }} aria-label="Project">
            <option value="">All projects</option>
            {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
          </select>
          <select value={period} onChange={(e) => { setPeriod(e.target.value); reset(); }} aria-label="Period">
            <option value="">All months</option>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
            <option value="-created_at">Newest first</option>
            <option value="-period">Period (desc)</option>
            <option value="-total_amount">Amount (desc)</option>
            <option value="review_due_at">Review due (asc)</option>
          </select>
        </div>
        <ErrorBox error={error} />
        {loading && !data ? (
          <Loading />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Partner</th>
                  <th>Project</th>
                  <th>Period</th>
                  <th className="num">Amount</th>
                  <th>Status</th>
                  <th>Exceptions</th>
                  <th>Submitted</th>
                  <th>Review due</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((r) => (
                  <tr key={r.id} className="clickable" onClick={() => router.push(`/reports/${r.id}`)}>
                    <td><Link href={`/reports/${r.id}`}>{r.report_number}</Link></td>
                    <td>{r.partner_name}</td>
                    <td>{r.project_code}</td>
                    <td>{periodLabel(r.fiscal_year, r.period)}</td>
                    <td className="num"><Amount value={r.total_amount} ccy={r.currency} /></td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>{r.open_exceptions > 0 ? <Pill tone="warn">{r.open_exceptions} open</Pill> : <span className="muted">—</span>}</td>
                    <td className="small">{dateTime(r.submitted_at)}</td>
                    <td className="small">{r.review_due_at ? <span className={r.is_overdue ? "text-bad" : ""}>{dateTime(r.review_due_at)}{r.is_overdue ? " · overdue" : ""}</span> : "—"}</td>
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
