import { useState } from "react";

import Layout from "@/components/Layout";
import { Amount, Card, ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { ReportStatus } from "@/types";
import { MONTHS, pct } from "@/utils/format";

interface MonthlyRow {
  partner: string;
  project: string;
  cost_category: string;
  gl_account: string;
  planned: string;
  actual_booked: string;
  actual_pending: string;
  variance: string;
  variance_pct: string | null;
  report_status: string;
}

const REGISTERS: { label: string; desc: string; status?: ReportStatus[] }[] = [
  { label: "All expense reports", desc: "Full register with approval dates" },
  { label: "Accepted reports", desc: "Auto-accepted and approved", status: ["AUTO_ACCEPTED", "APPROVED"] },
  { label: "Rejected reports", desc: "Rejected by PM or Finance", status: ["REJECTED"] },
  { label: "Returned reports", desc: "Waiting for partner clarification", status: ["RETURNED_FOR_CLARIFICATION"] },
  { label: "Pending reviews", desc: "PM and Finance queues", status: ["PENDING_PM_REVIEW", "PENDING_FINANCE_REVIEW"] },
];

export default function Exports() {
  const [fy, setFy] = useState(2026);
  const [period, setPeriod] = useState(9);
  const monthly = useApi(() => api.get<MonthlyRow[]>("/reports/monthly-variance", { fiscal_year: fy, period, format: "json" }), [fy, period]);
  const { error, run, busy } = useAction();

  return (
    <Layout roles={["PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"]}>
      <PageHeader
        title="Reports & exports"
        subtitle="Management reports in CSV / Excel. Every export is recorded in the audit trail."
        actions={
          <select value={fy} onChange={(e) => setFy(Number(e.target.value))} aria-label="Fiscal year">
            {[2025, 2026, 2027].map((y) => <option key={y}>{y}</option>)}
          </select>
        }
      />
      <ErrorBox error={error} />
      <div className="cards">
        {REGISTERS.map((r) => (
          <Card key={r.label} title={r.label}>
            <p className="small muted">{r.desc}</p>
            <div className="row gap">
              {(["xlsx", "csv"] as const).map((f) => (
                <button key={f} className="btn btn-ghost" disabled={busy} onClick={() => run(() => api.download("/reports/expense-reports/export", { fiscal_year: fy, status: r.status, format: f }))}>
                  ⇩ {f.toUpperCase()}
                </button>
              ))}
            </div>
          </Card>
        ))}
        <Card title="Top variances">
          <p className="small muted">Largest variance exceptions of the year with severity and outcome</p>
          <div className="row gap">
            {(["xlsx", "csv"] as const).map((f) => (
              <button key={f} className="btn btn-ghost" disabled={busy} onClick={() => run(() => api.download("/reports/top-variances/export", { fiscal_year: fy, format: f }))}>
                ⇩ {f.toUpperCase()}
              </button>
            ))}
          </div>
        </Card>
      </div>

      <Card
        title="Monthly variance report"
        actions={
          <div className="row gap">
            <select value={period} onChange={(e) => setPeriod(Number(e.target.value))} aria-label="Month">
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
            {(["xlsx", "csv"] as const).map((f) => (
              <button key={f} className="btn btn-ghost" onClick={() => run(() => api.download("/reports/monthly-variance", { fiscal_year: fy, period, format: f }))}>
                ⇩ {f.toUpperCase()}
              </button>
            ))}
          </div>
        }
      >
        {monthly.loading && <Loading />}
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr>
                <th>Partner</th><th>Project</th><th>Category</th><th>GL</th>
                <th className="num">Planned</th><th className="num">Booked</th><th className="num">Pending</th>
                <th className="num">Variance</th><th className="num">%</th><th>Report</th>
              </tr>
            </thead>
            <tbody>
              {monthly.data?.map((r, i) => (
                <tr key={i}>
                  <td>{r.partner}</td><td>{r.project}</td><td>{r.cost_category}</td><td>{r.gl_account}</td>
                  <td className="num"><Amount value={r.planned} /></td>
                  <td className="num"><Amount value={r.actual_booked} /></td>
                  <td className="num"><Amount value={r.actual_pending} /></td>
                  <td className="num"><Amount value={r.variance} colored /></td>
                  <td className="num">{pct(r.variance_pct)}</td>
                  <td>{r.report_status === "NOT_SUBMITTED" ? <span className="muted small">not submitted</span> : <StatusBadge status={r.report_status as ReportStatus} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </Layout>
  );
}
