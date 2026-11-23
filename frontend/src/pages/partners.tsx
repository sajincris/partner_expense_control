import { useState } from "react";

import Layout from "@/components/Layout";
import { Card, ErrorBox, Field, Loading, Modal, PageHeader, Pagination, Pill } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Page, Partner } from "@/types";

type Form = { id?: number; code: string; name: string; registration_number: string; country: string; contact_email: string; is_active: boolean };
const EMPTY: Form = { code: "", name: "", registration_number: "", country: "", contact_email: "", is_active: true };

export default function Partners() {
  const { hasRole } = useAuth();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi(() => api.get<Page<Partner>>("/partners", { q, page, size: 20 }), [q, page]);
  const [form, setForm] = useState<Form | null>(null);
  const action = useAction();
  const admin = hasRole("FINANCE_LEAD");

  const save = async () => {
    if (!form) return;
    const { id, code, ...rest } = form;
    const body = { ...rest, country: rest.country || null, registration_number: rest.registration_number || null, contact_email: rest.contact_email || null };
    const ok = await action.run(() => (id ? api.patch(`/partners/${id}`, body) : api.post("/partners", { code, ...body })));
    if (ok) {
      setForm(null);
      void reload();
    }
  };

  return (
    <Layout roles={["FINANCE_LEAD", "FINANCE_OFFICER", "AUDITOR"]}>
      <PageHeader title="Partners" subtitle="Implementing partner organisations" actions={admin && <button className="btn btn-primary" onClick={() => setForm(EMPTY)}>+ New partner</button>} />
      <Card>
        <div className="filters">
          <input placeholder="Search name or code…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <ErrorBox error={error} />
        {loading && !data && <Loading />}
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Code</th><th>Name</th><th>Registration</th><th>Country</th><th>Contact</th><th>Status</th>{admin && <th />}</tr>
            </thead>
            <tbody>
              {data?.items.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.code}</td>
                  <td>{p.name}</td>
                  <td className="small">{p.registration_number ?? "—"}</td>
                  <td>{p.country ?? "—"}</td>
                  <td className="small">{p.contact_email ?? "—"}</td>
                  <td>{p.is_active ? <Pill tone="good">active</Pill> : <Pill>inactive</Pill>}</td>
                  {admin && (
                    <td>
                      <button className="btn btn-ghost small" onClick={() => setForm({ id: p.id, code: p.code, name: p.name, registration_number: p.registration_number ?? "", country: p.country ?? "", contact_email: p.contact_email ?? "", is_active: p.is_active })}>
                        Edit
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Card>
      <Modal
        open={!!form}
        title={form?.id ? `Edit ${form.code}` : "New partner"}
        onClose={() => setForm(null)}
        footer={<><button className="btn btn-ghost" onClick={() => setForm(null)}>Cancel</button><button className="btn btn-primary" onClick={save} disabled={action.busy}>Save</button></>}
      >
        {form && (
          <div className="form-grid two">
            <ErrorBox error={action.error} />
            <Field label="Code" hint="Uppercase letters, digits, dashes"><input value={form.code} disabled={!!form.id} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} /></Field>
            <Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Registration number"><input value={form.registration_number} onChange={(e) => setForm({ ...form, registration_number: e.target.value })} /></Field>
            <Field label="Country (ISO-2)"><input value={form.country} maxLength={2} onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })} /></Field>
            <Field label="Contact email"><input value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} /></Field>
            <label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active</label>
          </div>
        )}
      </Modal>
    </Layout>
  );
}
