import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { EntityTotals, PeriodPoint } from "@/types";
import { compact, money, MONTHS } from "@/utils/format";

const C = { plan: "#94a3b8", actual: "#1d4ed8", pending: "#f59e0b", ytdPlan: "#64748b", ytdActual: "#0f766e", over: "#dc2626" };

export function PlanVsActualChart({ data }: { data: PeriodPoint[] }) {
  const rows = data.map((d) => ({
    name: MONTHS[d.period - 1],
    Planned: Number(d.planned),
    Actual: Number(d.actual),
    Pending: Number(d.pending),
    "YTD planned": Number(d.ytd_planned),
    "YTD actual": Number(d.ytd_actual),
  }));
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} />
        <YAxis yAxisId="m" tickFormatter={compact} tickLine={false} axisLine={false} fontSize={12} width={56} />
        <YAxis yAxisId="y" orientation="right" tickFormatter={compact} tickLine={false} axisLine={false} fontSize={12} width={56} />
        <Tooltip formatter={(v: unknown) => money(Number(v))} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar yAxisId="m" dataKey="Planned" fill={C.plan} radius={[3, 3, 0, 0]} />
        <Bar yAxisId="m" dataKey="Actual" fill={C.actual} radius={[3, 3, 0, 0]} />
        <Bar yAxisId="m" dataKey="Pending" fill={C.pending} radius={[3, 3, 0, 0]} />
        <Line yAxisId="y" type="monotone" dataKey="YTD planned" stroke={C.ytdPlan} strokeDasharray="5 4" dot={false} strokeWidth={2} />
        <Line yAxisId="y" type="monotone" dataKey="YTD actual" stroke={C.ytdActual} dot={false} strokeWidth={2} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function UtilizationChart({ data }: { data: EntityTotals[] }) {
  const rows = data.map((d) => ({ name: d.code, Utilization: d.utilization_pct ? Number(d.utilization_pct) : 0, over: d.over_budget }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 44)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis type="number" domain={[0, (max: number) => Math.max(100, Math.ceil(max / 10) * 10)]} tickFormatter={(v: number) => `${v}%`} fontSize={12} />
        <YAxis type="category" dataKey="name" width={90} fontSize={12} tickLine={false} axisLine={false} />
        <Tooltip formatter={(v: unknown) => `${Number(v).toFixed(1)}% of annual plan used`} />
        <Bar dataKey="Utilization" radius={[0, 3, 3, 0]}>
          {rows.map((r) => (
            <Cell key={r.name} fill={r.over ? C.over : C.actual} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
