import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";

import Layout from "@/components/Layout";
import { AuditPanel } from "@/components/ReportPanels";
import { Amount, Card, ErrorBox, Field, Loading, Modal, PageHeader, Pill } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { BudgetLine, BudgetPlan, BudgetVersion } from "@/types";
import { dateTime, MONTHS } from "@/utils/format";

type VersionDetail = BudgetVersion & { lines: BudgetLine[] };

export default function BudgetPlanPage() {
  const router = useRouter();
  const id = Number(router.query.id);
  const { hasRole, user } = useAuth();
  const plan = useApi(() => api.get<BudgetPlan>(`/budget-plans/${id}`), [id], !!id);
  const [versionId, setVersionId] = useState<number | null>(null);
  const version = useApi(() => api.get<VersionDetail>(`/budget-plans/${id}/versions/${versionId}`), [id, versionId], !!id && !!versionId);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [reason, setReason] = useState("");
  const action = useAction();

  useEffect(() => {
    if (plan.data && versionId === null) {
      const active = plan.data.versions.find((v) => v.status === "ACTIVE") ?? plan.data.versions[plan.data.versions.length - 1];
      if (active) setVersionId(active.id);
    }
  }, [plan.data, versionId]);

  // Pivot lines: rows = category/GL, columns = months
  const grid = useMemo(() => {
    const rows = new Map<string, { label: string; cat: number; gl: number; months: Record<number, string> }>();
    version.data?.lines.forEach((l) => {
      const key = `${l.cost_category_id}-${l.gl_account_id}`;
      if (!rows.has(key)) rows.set(key, { label: `${l.cost_category_name} · ${l.gl_account_number}`, cat: l.cost_category_id, gl: l.gl_account_id, months: {} });
      rows.get(key)!.months[l.period] = l.planned_amount;
    });
    return Array.from(rows.entries());
  }, [version.data]);

  if (!plan.data) return <Layout>{plan.error ? <ErrorBox error={plan.error} /> : <Loading />}</Layout>;
  const p = plan.data;
  const v = version.data;
  const canPlan = hasRole("FINANCE_OFFICER", "FINANCE_LEAD");
  const canActivate = hasRole("FINANCE_LEAD") && v?.status === "DRAFT" && v.created_by_id !== user?.id;

  const startReforecast = () => {
    const d: Record<string, string> = {};
    grid.forEach(([key, row]) => {
      for (let m = 1; m <= 12; m++) d[`${key}|${m}`] = row.months[m] ?? "0.00";
    });
    setDraft(d);
  };
  const saveVersion = async () => {
    if (!draft) return;
    const lines = Object.entries(draft).map(([k, amount]) => {
      const [key, m] = k.split("|");
      const [cat, gl] = key.split("-").map(Number);
      return { period: Number(m), cost_category_id: cat, gl_account_id: gl, planned_amount: amount || "0" };
    });
    const res = await action.run(() => api.post<BudgetVersion>(`/budget-plans/${id}/versions`, { change_reason: reason, lines }));
    if (res) {
      setDraft(null);
      setReason("");
      await plan.reload();
      setVersionId(res.id);
    }
  };
  const activate = async () => {
    if (!v) return;
    const res = await action.run(() => api.post(`/budget-plans/${id}/versions/${v.id}/activate`));
    if (res) {
      await plan.reload();
      void version.reload();
    }
  };

  const monthTotal = (m: number) => grid.reduce((s, [, row]) => s + Number(row.months[m] ?? 0), 0);

  return (
    <Layout>
      <PageHeader
        title={p.name}
        subtitle={`${p.partner_name} · ${p.project_code} ${p.project_name} · FY${p.fiscal_year} · ${p.currency}`}
        actions={canPlan && <button className="btn btn-primary" onClick={startReforecast} disabled={!v}>New version (reforecast)</button>}
      />
      <ErrorBox error={action.error} />
      <Card title="Versions">
        <div className="versions">
          {p.versions.map((ver) => (
            <button key={ver.id} className={`version ${ver.id === versionId ? "active" : ""}`} onClick={() => setVersionId(ver.id)}>
              <span>
                <strong>v{ver.version_no}</strong>{" "}
                <Pill tone={ver.status === "ACTIVE" ? "good" : ver.status === "DRAFT" ? "warn" : "neutral"}>{ver.status}</Pill>
              </span>
              <Amount value={ver.total_amount} />
              <span className="small muted">{ver.change_reason}</span>
              <span className="small muted">{ver.approved_at ? `activated ${dateTime(ver.approved_at)}` : `created ${dateTime(ver.created_at)}`}</span>
            </button>
          ))}
        </div>
        {v?.status === "DRAFT" && (
          <div className="alert alert-warn row between">
            <span>Version v{v.version_no} is a DRAFT: it does not affect variance checks until activated by a Finance Lead other than its creator.</span>
            {canActivate && <button className="btn btn-primary" onClick={activate} disabled={action.busy}>Activate v{v.version_no}</button>}
          </div>
        )}
      </Card>

      <Card title={v ? `Monthly plan — v${v.version_no}` : "Monthly plan"}>
        {version.loading && <Loading />}
        <div className="table-wrap">
          <table className="table compact grid-table">
            <thead>
              <tr>
                <th>Category · GL</th>
                {MONTHS.map((m) => <th key={m} className="num">{m}</th>)}
                <th className="num">Year</th>
              </tr>
            </thead>
            <tbody>
              {grid.map(([key, row]) => (
                <tr key={key}>
                  <td className="nowrap">{row.label}</td>
                  {MONTHS.map((_, i) => <td key={i} className="num"><Amount value={row.months[i + 1] ?? "0"} /></td>)}
                  <td className="num strong"><Amount value={String(Object.values(row.months).reduce((s, x) => s + Number(x), 0))} /></td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Total</td>
                {MONTHS.map((_, i) => <td key={i} className="num"><Amount value={String(monthTotal(i + 1))} /></td>)}
                <td className="num"><Amount value={v?.total_amount} /></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>

      <AuditPanel entityType="budget_plan_versions" entityId={versionId ?? 0} title="Version audit history" />

      <Modal
        open={!!draft}
        wide
        title="New budget version (reforecast)"
        onClose={() => setDraft(null)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setDraft(null)}>Cancel</button>
            <button className="btn btn-primary" disabled={reason.trim().length < 5 || action.busy} onClick={saveVersion}>Save as DRAFT</button>
          </>
        }
      >
        <ErrorBox error={action.error} />
        <Field label="Change reason (mandatory)">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Donor amendment no. 2 — supplies reallocated to Q4" />
        </Field>
        <div className="table-wrap">
          <table className="table compact grid-table">
            <thead>
              <tr>
                <th>Category · GL</th>
                {MONTHS.map((m) => <th key={m}>{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {draft && grid.map(([key, row]) => (
                <tr key={key}>
                  <td className="nowrap">{row.label}</td>
                  {MONTHS.map((_, i) => (
                    <td key={i}>
                      <input className="cell-input" inputMode="decimal" value={draft[`${key}|${i + 1}`]} onChange={(e) => setDraft({ ...draft, [`${key}|${i + 1}`]: e.target.value })} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Modal>
    </Layout>
  );
}
