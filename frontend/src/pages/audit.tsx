import { useState } from "react";

import Layout from "@/components/Layout";
import { AuditList } from "@/components/ReportPanels";
import { Card, ErrorBox, Loading, PageHeader, Pagination } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { AuditLog, Page } from "@/types";

const ENTITIES = [
  "expense_reports", "expense_lines", "expense_attachments", "variance_reviews", "budget_plans", "budget_plan_versions",
  "budget_plan_lines", "tolerance_rules", "system_settings", "users", "user_roles", "partners", "projects", "reporting_periods", "reports",
];
const ACTIONS = ["CREATE", "UPDATE", "STATUS_CHANGE", "SOFT_DELETE", "DELETE", "SUBMIT", "RESUBMIT", "AUTO_ACCEPT", "ROUTE_TO_PM", "APPROVE", "REJECT", "RETURN", "CANCEL", "ACTIVATE", "CONFIG_CHANGE", "UPLOAD", "EXPORT", "IMPORT", "LOGIN", "LOGIN_FAILED"];

export default function Audit() {
  const [entityType, setEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, loading } = useApi(
    () => api.get<Page<AuditLog>>("/audit-logs", {
      entity_type: entityType, entity_id: entityId, action, page, size: 25,
      date_from: from ? `${from}T00:00:00Z` : undefined, date_to: to ? `${to}T23:59:59Z` : undefined,
    }),
    [entityType, entityId, action, from, to, page],
  );
  const reset = () => setPage(1);

  return (
    <Layout roles={["FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR", "PROJECT_MANAGER"]}>
      <PageHeader title="Audit trail" subtitle="Append-only record of every change: who, when, from which request, old and new values" />
      <Card>
        <div className="filters">
          <select value={entityType} onChange={(e) => { setEntityType(e.target.value); reset(); }} aria-label="Entity">
            <option value="">All entities</option>
            {ENTITIES.map((e) => <option key={e}>{e}</option>)}
          </select>
          <input placeholder="Entity id" value={entityId} onChange={(e) => { setEntityId(e.target.value); reset(); }} style={{ width: 110 }} />
          <select value={action} onChange={(e) => { setAction(e.target.value); reset(); }} aria-label="Action">
            <option value="">All actions</option>
            {ACTIONS.map((a) => <option key={a}>{a}</option>)}
          </select>
          <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); reset(); }} aria-label="From" />
          <input type="date" value={to} onChange={(e) => { setTo(e.target.value); reset(); }} aria-label="To" />
        </div>
        <ErrorBox error={error} />
        {loading && !data ? <Loading /> : data && <AuditList logs={data.items} />}
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Card>
    </Layout>
  );
}
