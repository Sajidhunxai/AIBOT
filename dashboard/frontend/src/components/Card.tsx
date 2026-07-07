import type { ReactNode } from "react";

export function Card({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`card ${className}`}>
      <h3 className="card-title">{title}</h3>
      {children}
    </div>
  );
}

export function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="stat-box">
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={{ color: color || "#e2e8f0" }}>
        {value}
      </span>
    </div>
  );
}

export function Badge({ children, variant = "default" }: { children: ReactNode; variant?: string }) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}
