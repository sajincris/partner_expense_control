import Link from "next/link";
import { useState } from "react";

import Layout from "@/components/Layout";
import { Amount, Card, ErrorBox, Field, Loading, Modal, PageHeader, Pagination, Pill } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { BudgetPlan, Page } from "@/types";

const SAMPLE = `partner_code,project_code,fiscal_year,period,cost_category_code,gl_account,planned_amount,currency
HBA,WASH-2026,2027,1,PERS,6100,8200.00,USD
HBA,WASH-2026,2027,1,SUPP,6300,4500.00,USD`;

export default function Budgets() {
  const { hasRole } = useAuth();
  const [fy, setFy] = useState("2026");
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi(() => api.get<Page<BudgetPlan>>("/budget-plans", { fiscal_year: fy, page, size: 20 }), [fy, page]);
  const [importOpen, setImportOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const action = useAction();
  const canPlan = hasRole("FINANCE_OFFICER", "FINANCE_LEAD");

  const doImport = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("change_reason", reason);
    const res = await action.run(() => api.upload<{ plans_created: number; versions_created: number; lines_imported: number }>("/budget-plans/import", fd));
    if (res) {
      setResult(`Imported ${res.lines_imported} lines into ${res.versions_created} DRAFT version(s) (${res.plans_created} new plan(s)). Activate them on the plan page.`);
      void reload();
    }
  };

  return (
    <Layout>
      <PageHeader
        title="Budget plans"
        subtitle="Approved plans per partner, project and fiscal year — versioned, activated under maker-checker"
        actions={
          <>
            <select value={fy} onChange={(e) => { setFy(e.target.value); setPage(1); }} aria-label="Fiscal year">
              {["2025", "2026", "2027"].map((y) => <option key={y}>{y}</option>)}
            </select>
            {canPlan && <button className="btn btn-primary" onClick={() => setImportOpen(true)}>⇧ Upload plan (CSV)</button>}
          </>
        }
      />
      <Card>
        <ErrorBox error={error} />
        {loading && !data && <Loading />}
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Plan</th>
                <th>Partner</th>
                <th>Project</th>
                <th>FY</th>
                <th>Active version</th>
                <th className="num">Annual total</th>
                <th>Versions</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((p) => (
                <tr key={p.id}>
                  <td><Link href={`/budgets/${p.id}`}>{p.name}</Link></td>
                  <td>{p.partner_name}</td>
                  <td>{p.project_code}</td>
                  <td>{p.fiscal_year}</td>
                  <td>{p.active_version_no ? <Pill tone="good">v{p.active_version_no}</Pill> : <Pill tone="warn">none active</Pill>}</td>
                  <td className="num"><Amount value={p.active_total} ccy={p.currency} /></td>
                  <td>
                    {p.versions.map((v) => (
                      <Pill key={v.id} tone={v.status === "ACTIVE" ? "good" : v.status === "DRAFT" ? "warn" : "neutral"}>
                        v{v.version_no} {v.status.toLowerCase()}
                      </Pill>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Card>

      <Modal
        open={importOpen}
        title="Upload budget plan lines"
        onClose={() => { setImportOpen(false); setResult(null); }}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setImportOpen(false)}>Close</button>
            <button className="btn btn-primary" disabled={!file || reason.trim().length < 5 || action.busy} onClick={doImport}>Import as DRAFT</button>
          </>
        }
      >
        <p className="small muted">
          The file is validated as a whole: if any row is invalid nothing is imported. Each partner/project/year becomes a new DRAFT version that a Finance Lead
          (other than you) must activate.
        </p>
        <ErrorBox error={action.error} />
        {result && <div className="alert alert-good">{result}</div>}
        <Field label="CSV file">
          <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <Field label="Change reason (stored on the version and in the audit trail)">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. FY2027 budget approved by donor on 15 Dec" />
        </Field>
        <pre className="code small">{SAMPLE}</pre>
      </Modal>
    </Layout>
  );
}
