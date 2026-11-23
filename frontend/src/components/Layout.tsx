import Link from "next/link";
import { useRouter } from "next/router";
import { ReactNode, useEffect, useState } from "react";

import { homeFor, useAuth } from "@/context/AuthContext";
import { api } from "@/services/api";
import type { Notification, RoleCode } from "@/types";
import { dateTime } from "@/utils/format";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  roles: RoleCode[];
}

const ALL: RoleCode[] = ["PARTNER", "PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"];
const INTERNAL: RoleCode[] = ["PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"];

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Overview",
    items: [
      { href: "/partner", label: "My dashboard", icon: "◧", roles: ["PARTNER"] },
      { href: "/dashboard", label: "Plan vs actual", icon: "▤", roles: INTERNAL },
    ],
  },
  {
    section: "Operations",
    items: [
      { href: "/reports", label: "Expense reports", icon: "▦", roles: ALL },
      { href: "/exceptions", label: "Exception queue", icon: "⚑", roles: INTERNAL },
      { href: "/budgets", label: "Budget plans", icon: "▥", roles: ALL },
    ],
  },
  {
    section: "Control",
    items: [
      { href: "/exports", label: "Reports & exports", icon: "⇩", roles: INTERNAL },
      { href: "/audit", label: "Audit trail", icon: "⌕", roles: ["FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR", "PROJECT_MANAGER"] },
    ],
  },
  {
    section: "Administration",
    items: [
      { href: "/partners", label: "Partners", icon: "◎", roles: ["FINANCE_LEAD", "FINANCE_OFFICER", "AUDITOR"] },
      { href: "/projects", label: "Projects", icon: "◇", roles: INTERNAL },
      { href: "/users", label: "Users & roles", icon: "☰", roles: ["FINANCE_LEAD", "AUDITOR"] },
      { href: "/settings", label: "Rules & settings", icon: "⚙", roles: ["FINANCE_LEAD", "FINANCE_OFFICER", "AUDITOR"] },
    ],
  },
];

const ROLE_LABEL: Record<RoleCode, string> = {
  PARTNER: "Partner",
  PROJECT_MANAGER: "Project Manager",
  FINANCE_OFFICER: "Finance Officer",
  FINANCE_LEAD: "Finance Lead",
  AUDITOR: "Auditor",
};

export default function Layout({ children, roles }: { children: ReactNode; roles?: RoleCode[] }) {
  const { user, loading, logout, hasRole } = useAuth();
  const router = useRouter();
  const [notes, setNotes] = useState<Notification[]>([]);
  const [showNotes, setShowNotes] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) void router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (user) api.get<Notification[]>("/notifications").then(setNotes).catch(() => undefined);
  }, [user, router.asPath]);

  if (loading || !user) return <div className="loading full">Loading…</div>;

  const allowed = !roles || hasRole(...roles);
  const unread = notes.filter((n) => !n.read_at).length;

  const openNote = async (n: Notification) => {
    if (!n.read_at) await api.post(`/notifications/${n.id}/read`).catch(() => undefined);
    setShowNotes(false);
    if (n.entity_type === "expense_reports" && n.entity_id) void router.push(`/reports/${n.entity_id}`);
  };

  return (
    <div className={`shell ${menuOpen ? "menu-open" : ""}`}>
      <aside className="sidebar">
        <Link href={homeFor(user)} className="brand">
          <span className="brand-mark">PEC</span>
          <span>
            Partner Expense
            <br />
            <small>Control ERP</small>
          </span>
        </Link>
        <nav>
          {NAV.map((sec) => {
            const items = sec.items.filter((i) => hasRole(...i.roles));
            if (!items.length) return null;
            return (
              <div key={sec.section} className="nav-section">
                <span className="nav-title">{sec.section}</span>
                {items.map((i) => (
                  <Link key={i.href} href={i.href} className={`nav-link ${router.pathname.startsWith(i.href) ? "active" : ""}`} onClick={() => setMenuOpen(false)}>
                    <span className="nav-icon" aria-hidden>
                      {i.icon}
                    </span>
                    {i.label}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot small">Northbridge Humanitarian Fund · demo</div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost hamburger" onClick={() => setMenuOpen(!menuOpen)} aria-label="Menu">
            ☰
          </button>
          <div className="topbar-spacer" />
          <div className="notif">
            <button className="btn btn-ghost" onClick={() => setShowNotes(!showNotes)} aria-label="Notifications">
              🔔{unread > 0 && <span className="notif-count">{unread}</span>}
            </button>
            {showNotes && (
              <div className="notif-panel">
                {notes.length === 0 && <div className="empty small">No notifications</div>}
                {notes.slice(0, 12).map((n) => (
                  <button key={n.id} className={`notif-item ${n.read_at ? "" : "unread"}`} onClick={() => openNote(n)}>
                    <strong>{n.title}</strong>
                    <span className="small muted">{n.message}</span>
                    <span className="small muted">{dateTime(n.created_at)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="user-chip">
            <span className="avatar">{user.full_name.split(" ").map((p) => p[0]).join("").slice(0, 2)}</span>
            <span>
              <strong>{user.full_name}</strong>
              <br />
              <span className="small muted">{user.partner_name ? `${user.partner_name} · ` : ""}{user.roles.map((r) => ROLE_LABEL[r]).join(", ")}</span>
            </span>
          </div>
          <button className="btn btn-ghost" onClick={logout}>
            Sign out
          </button>
        </header>
        <main className="content">{allowed ? children : <div className="alert alert-bad">Your role does not have access to this screen.</div>}</main>
      </div>
    </div>
  );
}
