export function ComposioAuthRequired({ redirectUrl }: { redirectUrl: string }) {
  return (
    <div
      style={{
        background: "#fff7e8",
        border: "1px solid rgba(198, 144, 0, 0.35)",
        borderLeft: "6px solid #c69000",
        borderRadius: "10px",
        maxWidth: "560px",
        padding: "16px 18px",
      }}
    >
      <div
        style={{
          alignItems: "center",
          color: "#2a2a2a",
          display: "flex",
          fontSize: "1.05rem",
          fontWeight: 600,
          gap: "10px",
        }}
      >
        <span
          style={{
            alignItems: "center",
            background: "#fff1cf",
            borderRadius: "8px",
            color: "#9c6b00",
            display: "inline-flex",
            height: "28px",
            justifyContent: "center",
            width: "28px",
          }}
        >
          <i className="fa-regular fa-lock-keyhole" />
        </span>
        <span>Access Required</span>
      </div>

      <div
        style={{
          color: "#4a4a4a",
          fontSize: "0.98rem",
          marginTop: "8px",
        }}
      >
        Gooey.AI can&apos;t access this resource - it&apos;s private. Connect
        your account to continue.
      </div>

      <div style={{ marginTop: "14px" }}>
        <a
          href={redirectUrl}
          className="btn btn-theme btn-primary p-2 m-0"
          style={{ textDecoration: "none" }}
        >
          <i className="fa-solid fa-shield-check" /> Connect &amp; Grant Access
        </a>
      </div>

      <div
        style={{
          color: "#6b6b6b",
          fontSize: "0.8rem",
          marginTop: "8px",
        }}
      >
        Secure via Composio.io
      </div>
    </div>
  );
}
