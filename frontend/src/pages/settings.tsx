import { useState } from "react";

import Layout from "@/components/Layout";
import { Amount, Card, ErrorBox, Field, Loading, Modal, PageHeader, Pill } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { CostCategory, Page, Partner, Project, ReportingPeriod, Setting, ToleranceRule } from "@/types";
import { date, MONTHS } from "@/utils/format";

type RuleForm = Partial<ToleranceRule> & { change_reason?: string };

export default function Settings() {
  const { hasRole } = useAuth();
  const admin = hasRole("FINANCE_LEAD");
  const rules = useApi(() => api.get<ToleranceRule[]>("/config/tolerance-rules", { include_inactive: true }), []);
  const settings = useApi(() => api.get<Setting[]>("/config/settings"), []);
  const periods = useApi(() => api.get<ReportingPeriod[]>("/config/reporting-periods", { fiscal_year: 2026 }), []);
  const cats = useApi(() => api.get<CostCategory[]>("/master/cost-categories"), []);
  const projects = useApi(() => api.get<Page<Project>>("/projects", { size: 100 }), []);
  const partners = useApi(() => api.get<Page<Partner>>("/partners", { size: 100 }), []);
  const [rule, setRule] = useState<RuleForm | null>(null);
  const [setting, setSetting] = useState<{ key: string; value: string; reason: string } | null>(null);
  const action = useAction();

  const scopeLabel = (r: ToleranceRule) => {
    const parts = [
      r.project_id && `Project ${projects.data?.items.find((p) => p.id === r.project_id)?.code ?? r.project_id}`,
      r.partner_id && `Partner ${partners.data?.items.find((p) => p.id === r.partner_id)?.code ?? r.partner_id}`,
      r.cost_category_id && `Category ${cats.data?.find((c) => c.id === r.cost_category_id)?.name ?? r.cost_category_id}`,
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : "Global";
  };

  const saveRule = async () => {
    if (!rule) return;
    const ok = await action.run(() =>
      rule.id
        ? api.patch(`/config/tolerance-rules/${rule.id}`, {
            name: rule.name, max_variance_pct: rule.max_variance_pct, max_variance_abs: rule.max_variance_abs, direction: rule.direction,
            priority: rule.priority, is_active: rule.is_active, effective_to: rule.effective_to || null, change_reason: rule.change_reason,
          })
        : api.post("/config/tolerance-rules", {
            ...rule, project_id: rule.project_id || null, partner_id: rule.partner_id || null, cost_category_id: rule.cost_category_id || null,
            effective_to: rule.effective_to || null,
          }),
    );
    if (ok) {
      setRule(null);
      void rules.reload();
    }
  };
  const saveSetting = async () => {
    if (!setting) return;
    let value: unknown = setting.value;
    if (setting.value === "true" || setting.value === "false") value = setting.value === "true";
    else if (/^\d+$/.test(setting.value)) value = Number(setting.value);
    const ok = await action.run(() => api.put(`/config/settings/${setting.key}`, { value, change_reason: setting.reason }));
    if (ok) {
      setSetting(null);
      void settings.reload();
    }
  };
  const togglePeriod = async (p: ReportingPeriod) => {
    await action.run(() => api.patch(`/config/reporting-periods/${p.id}`, { ...p, status: p.status === "OPEN" ? "CLOSED" : "OPEN" }));
    void periods.reload();
  };

  return (
    <Layout roles={["FINANCE_LEAD", "FINANCE_OFFICER", "AUDITOR"]}>
      <PageHeader title="Rules & settings" subtitle="Variance tolerance rules, workflow settings and reporting periods. Every change requires a reason and is audited." />
      <ErrorBox error={action.error} />
      <Card
        title="Tolerance rules"
        actions={admin && (
          <button className="btn btn-primary" onClick={() => setRule({ name: "", max_variance_pct: "5", max_variance_abs: "500.00", abs_currency: "USD", direction: "OVERSPEND_ONLY", priority: 100, effective_from: "2026-01-01", is_active: true })}>
            + New rule
          </button>
        )}
      >
        <p className="small muted">
          A line is <strong>within tolerance</strong> when |variance %| ≤ limit <strong>and</strong> |variance| ≤ amount limit. The most specific active rule wins
          (project &gt; partner &gt; category &gt; global, then priority). If no rule applies, the report goes to manual review (fail-safe).
        </p>
        {rules.loading && <Loading />}
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Rule</th><th>Scope</th><th className="num">Max %</th><th className="num">Max amount</th><th>Direction</th><th className="num">Priority</th><th>Effective</th><th>Status</th>{admin && <th />}</tr></thead>
            <tbody>
              {rules.data?.map((r) => (
                <tr key={r.id} className={r.is_active ? "" : "row-muted"}>
                  <td><strong>{r.name}</strong><div className="small muted">{r.description}</div></td>
                  <td>{scopeLabel(r)}</td>
                  <td className="num">{Number(r.max_variance_pct).toFixed(2)}%</td>
                  <td className="num"><Amount value={r.max_variance_abs} ccy={r.abs_currency} /></td>
                  <td><Pill tone="info">{r.direction === "BOTH" ? "over & under" : "overspend only"}</Pill></td>
                  <td className="num">{r.priority}</td>
                  <td className="small">{date(r.effective_from)} → {r.effective_to ? date(r.effective_to) : "open"}</td>
                  <td>{r.is_active ? <Pill tone="good">active</Pill> : <Pill>inactive</Pill>}</td>
                  {admin && <td><button className="btn btn-ghost small" onClick={() => setRule({ ...r, change_reason: "" })}>Edit</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid-2">
        <Card title="Workflow settings">
          <table className="table compact">
            <tbody>
              {settings.data?.map((s) => (
                <tr key={s.key}>
                  <td><strong className="mono small">{s.key}</strong><div className="small muted">{s.description}</div></td>
                  <td className="nowrap">{String(s.value)}</td>
                  {admin && <td><button className="btn btn-ghost small" onClick={() => setSetting({ key: s.key, value: String(s.value), reason: "" })}>Change</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Reporting periods 2026">
          <div className="periods">
            {periods.data?.map((p) => (
              <button key={p.id} className={`period ${p.status === "OPEN" ? "open" : "closed"}`} disabled={!admin} onClick={() => togglePeriod(p)} title={`Deadline ${date(p.submission_deadline)} — click to ${p.status === "OPEN" ? "close" : "reopen"}`}>
                <strong>{MONTHS[p.period - 1]}</strong>
                <span className="small">{p.status}</span>
              </button>
            ))}
          </div>
          <p className="small muted">Closed periods refuse new submissions (setting <span className="mono">require_open_period</span>).</p>
        </Card>
      </div>

      <Modal open={!!rule} title={rule?.id ? `Edit rule: ${rule.name}` : "New tolerance rule"} onClose={() => setRule(null)}
        footer={<><button className="btn btn-ghost" onClick={() => setRule(null)}>Cancel</button><button className="btn btn-primary" disabled={action.busy || (!!rule?.id && (rule.change_reason ?? "").trim().length < 5)} onClick={saveRule}>Save</button></>}>
        {rule && (
          <div className="form-grid two">
            <ErrorBox error={action.error} />
            <Field label="Name"><input value={rule.name ?? ""} onChange={(e) => setRule({ ...rule, name: e.target.value })} /></Field>
            {!rule.id && (
              <>
                <Field label="Project (optional)">
                  <select value={rule.project_id ?? ""} onChange={(e) => setRule({ ...rule, project_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Any</option>
                    {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
                  </select>
                </Field>
                <Field label="Partner (optional)">
                  <select value={rule.partner_id ?? ""} onChange={(e) => setRule({ ...rule, partner_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Any</option>
                    {partners.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </Field>
                <Field label="Cost category (optional)">
                  <select value={rule.cost_category_id ?? ""} onChange={(e) => setRule({ ...rule, cost_category_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Any</option>
                    {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </Field>
                <Field label="Effective from"><input type="date" value={rule.effective_from ?? ""} onChange={(e) => setRule({ ...rule, effective_from: e.target.value })} /></Field>
              </>
            )}
            <Field label="Max variance %"><input inputMode="decimal" value={rule.max_variance_pct ?? ""} onChange={(e) => setRule({ ...rule, max_variance_pct: e.target.value })} /></Field>
            <Field label="Max variance amount (USD)"><input inputMode="decimal" value={rule.max_variance_abs ?? ""} onChange={(e) => setRule({ ...rule, max_variance_abs: e.target.value })} /></Field>
            <Field label="Direction">
              <select value={rule.direction} onChange={(e) => setRule({ ...rule, direction: e.target.value as ToleranceRule["direction"] })}>
                <option value="OVERSPEND_ONLY">Overspend only</option>
                <option value="BOTH">Over- and under-spend</option>
              </select>
            </Field>
            <Field label="Priority (lower wins on ties)"><input type="number" value={rule.priority ?? 100} onChange={(e) => setRule({ ...rule, priority: Number(e.target.value) })} /></Field>
            <Field label="Effective to (optional)"><input type="date" value={rule.effective_to ?? ""} onChange={(e) => setRule({ ...rule, effective_to: e.target.value || null })} /></Field>
            <label className="checkbox"><input type="checkbox" checked={!!rule.is_active} onChange={(e) => setRule({ ...rule, is_active: e.target.checked })} /> Active</label>
            {rule.id && <Field label="Change reason (mandatory, audited)"><input value={rule.change_reason ?? ""} onChange={(e) => setRule({ ...rule, change_reason: e.target.value })} /></Field>}
          </div>
        )}
      </Modal>

      <Modal open={!!setting} title={`Change ${setting?.key}`} onClose={() => setSetting(null)}
        footer={<><button className="btn btn-ghost" onClick={() => setSetting(null)}>Cancel</button><button className="btn btn-primary" disabled={(setting?.reason ?? "").trim().length < 5} onClick={saveSetting}>Save</button></>}>
        {setting && (
          <div className="form-grid">
            <Field label="Value" hint="BLOCK / REQUIRE_REVIEW, a number of days, or true / false"><input value={setting.value} onChange={(e) => setSetting({ ...setting, value: e.target.value })} /></Field>
            <Field label="Reason (audited)"><input value={setting.reason} onChange={(e) => setSetting({ ...setting, reason: e.target.value })} /></Field>
          </div>
        )}
      </Modal>
    </Layout>
  );
}
