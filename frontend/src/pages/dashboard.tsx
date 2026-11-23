import Link from "next/link";
import { useState } from "react";

import { PlanVsActualChart, UtilizationChart } from "@/components/Charts";
import Layout from "@/components/Layout";
import { Amount, Card, ErrorBox, KpiCard, Loading, PageHeader, Pill, SeverityBadge, StatusBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { DashboardSummary, EntityTotals, Page, PeriodPoint, Project, Partner, ReportStatus, TopVariance } from "@/types";
import { money, pct } from "@/utils/format";

const STATUS_ORDER: ReportStatus[] = [
  "AUTO_ACCEPTED", "APPROVED", "PENDING_PM_REVIEW", "PENDING_FINANCE_REVIEW", "RETURNED_FOR_CLARIFICATION", "REJECTED", "DRAFT", "CANCELLED",
];

export default function Dashboard() {
  const [fy, setFy] = useState(2026);
  const [projectId, setProjectId] = useState<string>("");
  const [partnerId, setPartnerId] = useState<string>("");

  const summary = useApi(() => api.get<DashboardSummary>("/dashboard/summary", { fiscal_year: fy }), [fy]);
  const series = useApi(
    () => api.get<PeriodPoint[]>("/dashboard/plan-vs-actual", { fiscal_year: fy, project_id: projectId, partner_id: partnerId }),
    [fy, projectId, partnerId],
  );
  const byProject = useApi(() => api.get<EntityTotals[]>("/dashboard/projects", { fiscal_year: fy }), [fy]);
  const byPartner = useApi(() => api.get<EntityTotals[]>("/dashboard/partners", { fiscal_year: fy }), [fy]);
  const top = useApi(() => api.get<TopVariance[]>("/dashboard/top-variances", { fiscal_year: fy, limit: 8 }), [fy]);
  const projects = useApi(() => api.get<Page<Project>>("/projects", { size: 100 }), []);
  const partners = useApi(() => api.get<Page<Partner>>("/partners", { size: 100 }), []);
  const s = summary.data;

  return (
    <Layout roles={["PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"]}>
      <PageHeader
        title="Plan vs actual"
        subtitle="Approved plans against accepted spend, with exceptions under review"
        actions={
          <select value={fy} onChange={(e) => setFy(Number(e.target.value))} aria-label="Fiscal year">
            {[2025, 2026, 2027].map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
        }
      />
      <ErrorBox error={summary.error} />
      {s ? (
        <div className="kpis">
          <KpiCard label="Planned (FY)" value={money(s.planned_total)} />
          <KpiCard label="Actual booked" value={money(s.actual_booked)} hint={`${pct(s.utilization_pct)} utilisation`} />
          <KpiCard label="Pending review" value={money(s.actual_pending_review)} tone="warn" hint={`${s.pending_pm_review} PM · ${s.pending_finance_review} Finance`} />
          <KpiCard label="Open exceptions" value={s.open_exceptions} tone={s.open_exceptions ? "warn" : "good"} />
          <KpiCard label="Overdue reviews" value={s.overdue_reviews} tone={s.overdue_reviews ? "bad" : "good"} hint="Past SLA" />
          <KpiCard label="Over-budget projects" value={s.over_budget_projects} tone={s.over_budget_projects ? "bad" : "good"} />
        </div>
      ) : (
        <Loading />
      )}

      {s && (
        <div className="status-strip">
          {STATUS_ORDER.map((st) => (
            <Link key={st} href={`/reports?status=${st}`} className="status-cell">
              <StatusBadge status={st} />
              <strong>{s.status_counts[st] ?? 0}</strong>
            </Link>
          ))}
        </div>
      )}

      <Card
        title="Monthly plan vs actual"
        actions={
          <div className="row gap">
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)} aria-label="Project">
              <option value="">All projects</option>
              {projects.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code}
                </option>
              ))}
            </select>
            <select value={partnerId} onChange={(e) => setPartnerId(e.target.value)} aria-label="Partner">
              <option value="">All partners</option>
              {partners.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        }
      >
        {series.data ? <PlanVsActualChart data={series.data} /> : <Loading />}
      </Card>

      <div className="grid-2">
        <Card title="Projects — budget utilisation">
          {byProject.data && <UtilizationChart data={byProject.data} />}
          <EntityTable rows={byProject.data ?? []} />
        </Card>
        <Card title="Partners — expense overview">
          <EntityTable rows={byPartner.data ?? []} />
        </Card>
      </div>

      <Card title="Top variances" actions={<Link href="/exports">Export →</Link>}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Report</th>
                <th>Partner / project</th>
                <th>Month</th>
                <th>Category</th>
                <th className="num">Planned</th>
                <th className="num">Actual</th>
                <th className="num">Variance</th>
                <th className="num">%</th>
                <th>Severity</th>
                <th>Report status</th>
              </tr>
            </thead>
            <tbody>
              {top.data?.map((t) => (
                <tr key={t.exception_id}>
                  <td><Link href={`/reports/${t.report_id}`}>{t.report_number}</Link></td>
                  <td>{t.partner_name} <span className="muted small">· {t.project_code}</span></td>
                  <td>{t.period}</td>
                  <td>{t.cost_category} <span className="muted small">{t.gl_account}</span></td>
                  <td className="num"><Amount value={t.planned} /></td>
                  <td className="num"><Amount value={t.actual} /></td>
                  <td className="num"><Amount value={t.variance} colored /></td>
                  <td className="num">{pct(t.variance_pct)}</td>
                  <td><SeverityBadge severity={t.severity} /></td>
                  <td><StatusBadge status={t.report_status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </Layout>
  );
}

function EntityTable({ rows }: { rows: EntityTotals[] }) {
  return (
    <div className="table-wrap">
      <table className="table compact">
        <thead>
          <tr>
            <th>Code</th>
            <th className="num">Planned</th>
            <th className="num">Actual</th>
            <th className="num">Pending</th>
            <th className="num">Remaining</th>
            <th className="num">Used</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td title={r.name}>
                <strong>{r.code}</strong> {r.over_budget && <Pill tone="bad">over budget</Pill>}
              </td>
              <td className="num"><Amount value={r.planned} /></td>
              <td className="num"><Amount value={r.actual} /></td>
              <td className="num"><Amount value={r.pending} /></td>
              <td className="num"><Amount value={r.remaining_budget} /></td>
              <td className="num">{pct(r.utilization_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

