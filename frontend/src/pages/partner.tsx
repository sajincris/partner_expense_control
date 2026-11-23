import Link from "next/link";
import { useState } from "react";

import { PlanVsActualChart } from "@/components/Charts";
import Layout from "@/components/Layout";
import { Amount, Card, Empty, ErrorBox, KpiCard, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { DashboardSummary, EntityTotals, Page, PeriodPoint, ReportSummary } from "@/types";
import { money, pct, periodLabel } from "@/utils/format";

export default function PartnerDashboard() {
  const { user } = useAuth();
  const [fy, setFy] = useState(2026);
  const summary = useApi(() => api.get<DashboardSummary>("/dashboard/summary", { fiscal_year: fy }), [fy]);
  const series = useApi(() => api.get<PeriodPoint[]>("/dashboard/plan-vs-actual", { fiscal_year: fy }), [fy]);
  const projects = useApi(() => api.get<EntityTotals[]>("/dashboard/projects", { fiscal_year: fy }), [fy]);
  const attention = useApi(
    () => api.get<Page<ReportSummary>>("/expense-reports", { status: ["DRAFT", "RETURNED_FOR_CLARIFICATION"], size: 10 }),
    [],
  );
  const recent = useApi(() => api.get<Page<ReportSummary>>("/expense-reports", { fiscal_year: fy, size: 8, sort: "-period" }), [fy]);
  const s = summary.data;

  return (
    <Layout roles={["PARTNER"]}>
      <PageHeader
        title={`Welcome, ${user?.full_name.split(" ")[0] ?? ""}`}
        subtitle={`${user?.partner_name ?? ""} · fiscal year ${fy}`}
        actions={
          <>
            <select value={fy} onChange={(e) => setFy(Number(e.target.value))} aria-label="Fiscal year">
              {[2025, 2026, 2027].map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
            <Link href="/reports/new" className="btn btn-primary">
              + New expense report
            </Link>
          </>
        }
      />
      <ErrorBox error={summary.error} />
      {s && (
        <div className="kpis">
          <KpiCard label="Approved budget" value={money(s.planned_total)} hint="Active plan versions" />
          <KpiCard label="Accepted spend" value={money(s.actual_booked)} hint={`${pct(s.utilization_pct)} of annual plan`} />
          <KpiCard label="Remaining budget" value={money(s.remaining_budget)} tone={Number(s.remaining_budget) < 0 ? "bad" : "good"} />
          <KpiCard label="Under review" value={s.pending_pm_review + s.pending_finance_review} hint={`${money(s.actual_pending_review)} awaiting decision`} tone="warn" />
          <KpiCard label="Returned to you" value={s.status_counts.RETURNED_FOR_CLARIFICATION} tone={s.status_counts.RETURNED_FOR_CLARIFICATION ? "bad" : "default"} hint="Needs clarification" />
        </div>
      )}

      <div className="grid-2">
        <Card title="Action required">
          {attention.loading && <Loading />}
          {attention.data && attention.data.items.length === 0 && <Empty>Nothing waiting for you.</Empty>}
          <ul className="list">
            {attention.data?.items.map((r) => (
              <li key={r.id}>
                <Link href={`/reports/${r.id}`}>
                  <strong>{r.report_number}</strong> · {r.project_code} · {periodLabel(r.fiscal_year, r.period)}
                </Link>
                <StatusBadge status={r.status} />
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Budget by project">
          {projects.data?.map((p) => (
            <div key={p.id} className="budget-row">
              <div className="row between">
                <span>
                  <strong>{p.code}</strong> <span className="muted small">{p.name}</span>
                </span>
                <span className="small">
                  <Amount value={p.actual} /> / <Amount value={p.planned} />
                </span>
              </div>
              <div className="progress">
                <div className={`progress-bar ${p.over_budget ? "bad" : ""}`} style={{ width: `${Math.min(100, Number(p.utilization_pct ?? 0))}%` }} />
              </div>
            </div>
          ))}
        </Card>
      </div>

      <Card title="Plan vs actual by month">{series.data ? <PlanVsActualChart data={series.data} /> : <Loading />}</Card>

      <Card title="Recent reports" actions={<Link href="/reports">All reports →</Link>}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Report</th>
                <th>Project</th>
                <th>Period</th>
                <th className="num">Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.data?.items.map((r) => (
                <tr key={r.id}>
                  <td><Link href={`/reports/${r.id}`}>{r.report_number}</Link></td>
                  <td>{r.project_code}</td>
                  <td>{periodLabel(r.fiscal_year, r.period)}</td>
                  <td className="num"><Amount value={r.total_amount} /></td>
                  <td><StatusBadge status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </Layout>
  );
}
