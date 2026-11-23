import { useRouter } from "next/router";
import { FormEvent, useState } from "react";

import Layout from "@/components/Layout";
import { Card, ErrorBox, Field, PageHeader } from "@/components/ui";
import { useApi, useAction } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Page, Project, ReportDetail, ReportingPeriod } from "@/types";
import { date, MONTHS } from "@/utils/format";

export default function NewReport() {
  const router = useRouter();
  const [projectId, setProjectId] = useState("");
  const [fy, setFy] = useState(2026);
  const [period, setPeriod] = useState("");
  const [comment, setComment] = useState("");
  const projects = useApi(() => api.get<Page<Project>>("/projects", { size: 100 }), []);
  const periods = useApi(() => api.get<ReportingPeriod[]>("/config/reporting-periods", { fiscal_year: fy }), [fy]);
  const { busy, error, run } = useAction();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const r = await run(() =>
      api.post<ReportDetail>("/expense-reports", { project_id: Number(projectId), fiscal_year: fy, period: Number(period), currency: "USD", partner_comment: comment || null }),
    );
    if (r) void router.push(`/reports/${r.id}`);
  };

  return (
    <Layout roles={["PARTNER"]}>
      <PageHeader title="New expense report" subtitle="Step 1 of 3 — choose project and reporting period. Lines and documents come next." />
      <div className="steps">
        <span className="step active">1 · Header</span>
        <span className="step">2 · Lines & documents</span>
        <span className="step">3 · Review & submit</span>
      </div>
      <Card>
        <form className="form-grid" onSubmit={submit}>
          <ErrorBox error={error} />
          <Field label="Project">
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)} required>
              <option value="">Select a project…</option>
              {projects.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Fiscal year">
            <select value={fy} onChange={(e) => setFy(Number(e.target.value))}>
              {[2026, 2027].map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
          </Field>
          <Field label="Reporting period" hint="Only OPEN periods accept submissions.">
            <select value={period} onChange={(e) => setPeriod(e.target.value)} required>
              <option value="">Select a month…</option>
              {periods.data?.map((p) => (
                <option key={p.id} value={p.period} disabled={p.status !== "OPEN"}>
                  {MONTHS[p.period - 1]} {p.fiscal_year} — {p.status === "OPEN" ? `deadline ${date(p.submission_deadline)}` : "closed"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Comment (optional)">
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={4000} />
          </Field>
          <div className="row gap">
            <button className="btn btn-primary" disabled={busy}>
              Create draft
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => router.back()}>
              Cancel
            </button>
          </div>
        </form>
      </Card>
    </Layout>
  );
}
