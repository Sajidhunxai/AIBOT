export default function NotFound() {
  return (
    <div className="card" style={{ padding: "1.5rem" }}>
      <h2 style={{ marginBottom: "0.75rem" }}>Page not found</h2>
      <p className="empty">
        <a href="/" style={{ color: "#3b82f6" }}>
          Back to dashboard
        </a>
      </p>
    </div>
  );
}
