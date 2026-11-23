import { useRouter } from "next/router";
import { FormEvent, useState } from "react";

import { ErrorBox } from "@/components/ui";
import { homeFor, useAuth } from "@/context/AuthContext";
import { ApiError } from "@/services/api";

const DEMO = [
  ["Partner (Hope Bridge)", "partner.hba@demo.local"],
  ["Partner (Danube Health)", "partner.dch@demo.local"],
  ["Project Manager (WASH, EDU)", "pm.wash@demo.local"],
  ["Project Manager (Health)", "pm.health@demo.local"],
  ["Finance Officer", "finance@demo.local"],
  ["Finance Lead / Admin", "admin@demo.local"],
  ["Auditor", "auditor@demo.local"],
];

export default function Login() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      void router.replace(homeFor(user));
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, "NETWORK", "Cannot reach the API"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-hero">
        <span className="brand-mark big">PEC</span>
        <h1>Partner Expense Control</h1>
        <p>Plan vs actual monitoring and variance approval for implementing-partner expenses.</p>
        <ul>
          <li>Configurable tolerance rules with automatic acceptance</li>
          <li>Two-step exception review: Project Manager → Finance</li>
          <li>Segregation of duties and a complete audit trail</li>
        </ul>
      </div>
      <form className="login-card" onSubmit={submit}>
        <h2>Sign in</h2>
        <ErrorBox error={error} />
        <label className="field">
          <span className="field-label">Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span className="field-label">Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <button className="btn btn-primary block" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div className="demo-users">
          <span className="small muted">Demo users (password Demo@2026!) — click to fill:</span>
          {DEMO.map(([label, mail]) => (
            <button
              type="button"
              key={mail}
              className="demo-user"
              onClick={() => {
                setEmail(mail);
                setPassword("Demo@2026!");
              }}
            >
              <strong>{label}</strong>
              <span className="small muted">{mail}</span>
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
