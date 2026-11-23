import { useState } from "react";

import Layout from "@/components/Layout";
import { Card, ErrorBox, Field, Loading, Modal, PageHeader, Pill } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Page, Partner, Project, User } from "@/types";
import { date } from "@/utils/format";

type Form = { id?: number; code: string; name: string; donor: string; start_date: string; end_date: string; currency: string; project_manager_id: string };
const EMPTY: Form = { code: "", name: "", donor: "", start_date: "", end_date: "", currency: "USD", project_manager_id: "" };

export default function Projects() {
  const { hasRole } = useAuth();
  const admin = hasRole("FINANCE_LEAD");
  const { data, error, loading, reload } = useApi(() => api.get<Page<Project>>("/projects", { size: 100 }), []);
  const pms = useApi(() => api.get<Page<User>>("/users", { role: "PROJECT_MANAGER", size: 100 }), [], admin);
  const partners = useApi(() => api.get<Page<Partner>>("/partners", { size: 100 }), [], admin);
  const [form, setForm] = useState<Form | null>(null);
  const [link, setLink] = useState<{ project: Project; partner_id: string; agreement_reference: string } | null>(null);
  const action = useAction();

  const save = async () => {
    if (!form) return;
    const body = { ...form, project_manager_id: form.project_manager_id ? Number(form.project_manager_id) : null, donor: form.donor || null };
    const { id, ...rest } = body;
    const ok = await action.run(() =>
      id ? api.patch(`/projects/${id}`, { name: rest.name, donor: rest.donor, end_date: rest.end_date, project_manager_id: rest.project_manager_id }) : api.post("/projects", rest),
    );
    if (ok) {
      setForm(null);
      void reload();
    }
  };
  const saveLink = async () => {
    if (!link) return;
    const ok = await action.run(() => api.post(`/projects/${link.project.id}/partners`, { partner_id: Number(link.partner_id), agreement_reference: link.agreement_reference || null }));
    if (ok) {
      setLink(null);
      void reload();
    }
  };

  return (
    <Layout roles={["PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"]}>
      <PageHeader title="Projects" subtitle="Projects, donors, responsible Project Managers and implementing partners" actions={admin && <button className="btn btn-primary" onClick={() => setForm(EMPTY)}>+ New project</button>} />
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      <div className="cards">
        {data?.items.map((p) => (
          <Card
            key={p.id}
            title={<>{p.code} <span className="muted small">{p.currency}</span></>}
            actions={admin && (
              <div className="row gap">
                <button className="btn btn-ghost small" onClick={() => setLink({ project: p, partner_id: "", agreement_reference: "" })}>+ Partner</button>
                <button className="btn btn-ghost small" onClick={() => setForm({ id: p.id, code: p.code, name: p.name, donor: p.donor ?? "", start_date: p.start_date, end_date: p.end_date, currency: p.currency, project_manager_id: String(p.project_manager_id ?? "") })}>Edit</button>
              </div>
            )}
          >
            <h3 className="project-name">{p.name}</h3>
            <dl className="dl">
              <dt>Donor</dt><dd>{p.donor ?? "—"}</dd>
              <dt>Duration</dt><dd>{date(p.start_date)} – {date(p.end_date)}</dd>
              <dt>Project Manager</dt><dd>{p.project_manager_name ?? <Pill tone="bad">unassigned</Pill>}</dd>
              <dt>Partners</dt>
              <dd>{p.partners.map((l) => <Pill key={l.id} tone="info">{l.partner_name}{l.agreement_reference ? ` · ${l.agreement_reference}` : ""}</Pill>)}</dd>
            </dl>
          </Card>
        ))}
      </div>

      <Modal open={!!form} title={form?.id ? `Edit ${form.code}` : "New project"} onClose={() => setForm(null)}
        footer={<><button className="btn btn-ghost" onClick={() => setForm(null)}>Cancel</button><button className="btn btn-primary" disabled={action.busy} onClick={save}>Save</button></>}>
        {form && (
          <div className="form-grid two">
            <ErrorBox error={action.error} />
            <Field label="Code"><input value={form.code} disabled={!!form.id} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} /></Field>
            <Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Donor"><input value={form.donor} onChange={(e) => setForm({ ...form, donor: e.target.value })} /></Field>
            <Field label="Project Manager">
              <select value={form.project_manager_id} onChange={(e) => setForm({ ...form, project_manager_id: e.target.value })}>
                <option value="">—</option>
                {pms.data?.items.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </select>
            </Field>
            <Field label="Start date"><input type="date" value={form.start_date} disabled={!!form.id} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
            <Field label="End date"><input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          </div>
        )}
      </Modal>

      <Modal open={!!link} title={`Link partner to ${link?.project.code}`} onClose={() => setLink(null)}
        footer={<><button className="btn btn-ghost" onClick={() => setLink(null)}>Cancel</button><button className="btn btn-primary" disabled={!link?.partner_id || action.busy} onClick={saveLink}>Link</button></>}>
        {link && (
          <div className="form-grid">
            <ErrorBox error={action.error} />
            <Field label="Partner">
              <select value={link.partner_id} onChange={(e) => setLink({ ...link, partner_id: e.target.value })}>
                <option value="">Select…</option>
                {partners.data?.items.filter((pt) => !link.project.partners.some((l) => l.partner_id === pt.id)).map((pt) => <option key={pt.id} value={pt.id}>{pt.name}</option>)}
              </select>
            </Field>
            <Field label="Agreement reference"><input value={link.agreement_reference} onChange={(e) => setLink({ ...link, agreement_reference: e.target.value })} /></Field>
          </div>
        )}
      </Modal>
    </Layout>
  );
}
