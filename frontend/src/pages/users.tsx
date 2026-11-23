import { useState } from "react";

import Layout from "@/components/Layout";
import { Card, ErrorBox, Field, Loading, Modal, PageHeader, Pagination, Pill } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Page, Partner, RoleCode, User } from "@/types";
import { dateTime } from "@/utils/format";

const ROLES: RoleCode[] = ["PARTNER", "PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"];

type Form = { id?: number; email: string; full_name: string; password: string; partner_id: string; roles: RoleCode[]; is_active: boolean };
const EMPTY: Form = { email: "", full_name: "", password: "", partner_id: "", roles: [], is_active: true };

export default function Users() {
  const { hasRole, user: me } = useAuth();
  const admin = hasRole("FINANCE_LEAD");
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi(() => api.get<Page<User>>("/users", { q, role, page, size: 20 }), [q, role, page]);
  const partners = useApi(() => api.get<Page<Partner>>("/partners", { size: 100 }), []);
  const [form, setForm] = useState<Form | null>(null);
  const action = useAction();

  const toggleRole = (r: RoleCode) => form && setForm({ ...form, roles: form.roles.includes(r) ? form.roles.filter((x) => x !== r) : [...form.roles, r] });

  const save = async () => {
    if (!form) return;
    const partner_id = form.partner_id ? Number(form.partner_id) : null;
    const ok = await action.run(async () => {
      if (!form.id) return api.post("/users", { email: form.email, full_name: form.full_name, password: form.password, partner_id, roles: form.roles });
      await api.patch(`/users/${form.id}`, { full_name: form.full_name, is_active: form.is_active, partner_id });
      return api.put(`/users/${form.id}/roles`, { roles: form.roles });
    });
    if (ok) {
      setForm(null);
      void reload();
    }
  };

  return (
    <Layout roles={["FINANCE_LEAD", "AUDITOR"]}>
      <PageHeader title="Users & roles" subtitle="Role-based access with segregation-of-duties checks on every assignment" actions={admin && <button className="btn btn-primary" onClick={() => setForm(EMPTY)}>+ New user</button>} />
      <div className="alert alert-info small">
        Blocked combinations: Partner + any internal approver role, and Project Manager + Finance Officer. Administrators cannot change their own roles.
      </div>
      <Card>
        <div className="filters">
          <input placeholder="Search email or name…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <select value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }}>
            <option value="">All roles</option>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>
        <ErrorBox error={error} />
        {loading && !data && <Loading />}
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Email</th><th>Roles</th><th>Partner</th><th>Last login</th><th>Status</th>{admin && <th />}</tr></thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td className="small">{u.email}</td>
                  <td>{u.roles.map((r) => <Pill key={r} tone="info">{r}</Pill>)}</td>
                  <td>{u.partner_name ?? "—"}</td>
                  <td className="small">{dateTime(u.last_login_at)}</td>
                  <td>{u.is_active ? <Pill tone="good">active</Pill> : <Pill>inactive</Pill>}</td>
                  {admin && (
                    <td>
                      <button className="btn btn-ghost small" disabled={u.id === me?.id} onClick={() => setForm({ id: u.id, email: u.email, full_name: u.full_name, password: "", partner_id: String(u.partner_id ?? ""), roles: u.roles, is_active: u.is_active })}>
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
      <Modal open={!!form} title={form?.id ? `Edit ${form.email}` : "New user"} onClose={() => setForm(null)}
        footer={<><button className="btn btn-ghost" onClick={() => setForm(null)}>Cancel</button><button className="btn btn-primary" disabled={action.busy || !form?.roles.length} onClick={save}>Save</button></>}>
        {form && (
          <div className="form-grid two">
            <ErrorBox error={action.error} />
            <Field label="Email"><input value={form.email} disabled={!!form.id} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Full name"><input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            {!form.id && <Field label="Initial password" hint="Min. 10 characters"><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>}
            <Field label="Partner organisation" hint="Required for Partner users only">
              <select value={form.partner_id} onChange={(e) => setForm({ ...form, partner_id: e.target.value })}>
                <option value="">— internal staff —</option>
                {partners.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <div className="field">
              <span className="field-label">Roles</span>
              {ROLES.map((r) => (
                <label key={r} className="checkbox"><input type="checkbox" checked={form.roles.includes(r)} onChange={() => toggleRole(r)} /> {r}</label>
              ))}
            </div>
            {form.id && <label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active</label>}
          </div>
        )}
      </Modal>
    </Layout>
  );
}
