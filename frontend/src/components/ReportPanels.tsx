import { useState } from "react";

import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { ApprovalAction, AuditLog, Page, VarianceException, VarianceResult } from "@/types";
import { EXCEPTION_LABEL, STATUS_LABEL, dateTime, pct } from "@/utils/format";

import { Amount, Card, Empty, ErrorBox, Loading, Pill, SeverityBadge } from "./ui";

/** Plan vs actual table for one report (calculation from the variance engine). */
export function VarianceTable({ reportId, currency }: { reportId: number; currency: string }) {
  const { data, error, loading } = useApi(() => api.get<VarianceResult>(`/expense-reports/${reportId}/variance`), [reportId]);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const t = data.totals;
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Cost category / GL</th>
              <th className="num">Planned</th>
              <th className="num">Actual</th>
              <th className="num">Variance</th>
              <th className="num">Var. %</th>
              <th className="num">YTD plan</th>
              <th className="num">YTD actual</th>
              <th className="num">Remaining</th>
              <th>Tolerance</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={`${r.cost_category_id}-${r.gl_account_id}`} className={r.within_tolerance ? "" : "row-flag"}>
                <td>
                  {r.cost_category_name} <span className="muted small">· {r.gl_account_number}</span>
                  {!r.has_plan_line && <Pill tone="bad">no plan line</Pill>}
                </td>
                <td className="num"><Amount value={r.planned} /></td>
                <td className="num"><Amount value={r.actual} /></td>
                <td className="num"><Amount value={r.variance} colored /></td>
                <td className="num">{pct(r.variance_pct)}</td>
                <td className="num"><Amount value={r.ytd_planned} /></td>
                <td className="num"><Amount value={r.ytd_actual} /></td>
                <td className="num"><Amount value={r.remaining_budget} colored={false} /></td>
                <td title={r.reason}>
                  {r.within_tolerance ? <Pill tone="good">within</Pill> : <Pill tone="bad">outside</Pill>}
                  <span className="muted small"> {r.rule_name ?? ""}</span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total ({currency})</td>
              <td className="num"><Amount value={t.total_planned as string} /></td>
              <td className="num"><Amount value={t.total_actual as string} /></td>
              <td className="num"><Amount value={t.total_variance as string} colored /></td>
              <td className="num">{pct(t.total_variance_pct as string | null)}</td>
              <td className="num"><Amount value={t.ytd_planned as string} /></td>
              <td className="num"><Amount value={t.ytd_actual as string} /></td>
              <td className="num"><Amount value={t.remaining_budget as string} /></td>
              <td>{data.auto_accept ? <Pill tone="good">auto-accept</Pill> : <Pill tone="warn">review required</Pill>}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      {data.findings.length > 0 && (
        <ul className="findings">
          {data.findings.map((f, i) => (
            <li key={i}>
              <SeverityBadge severity={f.severity} /> <strong>{EXCEPTION_LABEL[f.exception_type]}</strong> — {f.message}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function ExceptionList({ items }: { items: VarianceException[] }) {
  if (!items.length) return <Empty>No control exceptions.</Empty>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Type</th>
            <th>Severity</th>
            <th className="num">Planned</th>
            <th className="num">Actual</th>
            <th className="num">Variance</th>
            <th className="num">%</th>
            <th>Message</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id} className={e.status === "SUPERSEDED" ? "row-muted" : ""}>
              <td className="small muted">S{e.submission_no}</td>
              <td>{EXCEPTION_LABEL[e.exception_type]}</td>
              <td><SeverityBadge severity={e.severity} /></td>
              <td className="num"><Amount value={e.planned_amount} /></td>
              <td className="num"><Amount value={e.actual_amount} /></td>
              <td className="num"><Amount value={e.variance_amount} colored /></td>
              <td className="num">{pct(e.variance_pct)}</td>
              <td className="small">
                {e.message}
                {e.pm_justification && <div className="note">PM: {e.pm_justification}</div>}
                {e.finance_note && <div className="note">Finance: {e.finance_note}</div>}
              </td>
              <td><Pill tone={e.status === "OPEN" ? "warn" : e.status === "RESOLVED" ? "good" : e.status === "REJECTED" ? "bad" : "neutral"}>{e.status}</Pill></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ApprovalTimeline({ actions }: { actions: ApprovalAction[] }) {
  if (!actions.length) return <Empty>No workflow actions yet.</Empty>;
  return (
    <ol className="timeline">
      {actions.map((a) => (
        <li key={a.id} className={`tl-${a.action.toLowerCase()}`}>
          <div className="tl-head">
            <strong>{a.action.replace(/_/g, " ")}</strong>
            <span className="muted small">
              {a.stage} · {a.actor_name ?? "System"} · {dateTime(a.created_at)}
            </span>
          </div>
          <div className="small muted">
            {STATUS_LABEL[a.from_status]} → {STATUS_LABEL[a.to_status]}
          </div>
          {a.comment && <div className="tl-comment">“{a.comment}”</div>}
          {a.checklist && (
            <div className="small">
              {Object.entries(a.checklist).map(([k, v]) => (
                <Pill key={k} tone={v ? "good" : "bad"}>
                  {v ? "✓" : "✗"} {k.replace(/_/g, " ")}
                </Pill>
              ))}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Field-level audit history for one entity (old → new values). */
export function AuditPanel({ entityType, entityId, title = "Audit history" }: { entityType: string; entityId: number | string; title?: string }) {
  const [open, setOpen] = useState(false);
  const { data, loading, error } = useApi(
    () => api.get<Page<AuditLog>>("/audit-logs", { entity_type: entityType, entity_id: String(entityId), size: 100 }),
    [entityType, entityId, open],
    open,
  );
  return (
    <Card
      title={title}
      actions={
        <button className="btn btn-ghost" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </button>
      }
    >
      {!open && <span className="muted small">Every change to this record is logged with actor, timestamp and old/new values.</span>}
      {open && loading && <Loading />}
      {open && error && <ErrorBox error={error} />}
      {open && data && <AuditList logs={data.items} />}
    </Card>
  );
}

export function AuditList({ logs }: { logs: AuditLog[] }) {
  if (!logs.length) return <Empty>No audit entries.</Empty>;
  return (
    <ul className="audit-list">
      {logs.map((l) => (
        <li key={l.id}>
          <div className="row between">
            <span>
              <Pill tone="info">{l.action}</Pill> <strong>{l.entity_type}</strong> #{l.entity_id}
            </span>
            <span className="muted small">
              {l.actor_email ?? "system"} · {dateTime(l.created_at)}
            </span>
          </div>
          {l.comment && <div className="small">“{l.comment}”</div>}
          <Diff oldV={l.old_values} newV={l.new_values} />
        </li>
      ))}
    </ul>
  );
}

function Diff({ oldV, newV }: { oldV: Record<string, unknown> | null; newV: Record<string, unknown> | null }) {
  const keys = Array.from(new Set([...Object.keys(oldV ?? {}), ...Object.keys(newV ?? {})]));
  if (!keys.length) return null;
  const show = (v: unknown) => (v === null || v === undefined ? "∅" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return (
    <table className="diff">
      <tbody>
        {keys.slice(0, 14).map((k) => (
          <tr key={k}>
            <td className="muted">{k}</td>
            <td className="old">{oldV ? show(oldV[k]) : ""}</td>
            <td className="new">{newV ? show(newV[k]) : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
