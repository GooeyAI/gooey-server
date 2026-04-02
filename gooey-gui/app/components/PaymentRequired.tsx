type PaymentRequiredProps = {
  discordInviteUrl: string;
  paidOnlyModels: string[];
};

export function PaymentRequired({
  discordInviteUrl,
  paidOnlyModels,
}: PaymentRequiredProps) {
  return (
    <div
      style={{
        background: "#fff7e8",
        border: "1px solid rgba(198, 144, 0, 0.35)",
        borderLeft: "6px solid #c69000",
        borderRadius: "10px",
        maxWidth: "640px",
        padding: "16px 18px",
      }}
    >
      <div
        style={{
          alignItems: "center",
          color: "#2a2a2a",
          display: "flex",
          fontSize: "1.05rem",
          fontWeight: 650,
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
          <i className="fa-regular fa-credit-card" />
        </span>
        <span>Paid workspace required</span>
      </div>

      <div
        style={{
          color: "#4a4a4a",
          fontSize: "0.98rem",
          marginTop: "8px",
        }}
      >
        Your workflow requested paid-only model access.
      </div>

      {paidOnlyModels.length ? (
        <div
          style={{
            color: "#4a4a4a",
            fontSize: "0.95rem",
            marginTop: "12px",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: "6px" }}>Models:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {paidOnlyModels.map((model) => (
              <span
                key={model}
                style={{
                  alignItems: "center",
                  background: "#111827",
                  borderRadius: "999px",
                  color: "#ffffff",
                  display: "inline-flex",
                  fontSize: "0.85rem",
                  padding: "4px 10px",
                }}
              >
                {model}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "10px",
          marginTop: "14px",
        }}
      >
        <a
          href="/pricing/"
          target="_blank"
          className="btn btn-theme btn-primary p-2 m-0"
          style={{ textDecoration: "none" }}
        >
          <i className="fa-solid fa-bolt" /> View pricing
        </a>
        <a
          href="/account/"
          target="_blank"
          className="btn btn-outline-secondary p-2 m-0"
          style={{ textDecoration: "none" }}
        >
          <i className="fa-regular fa-user" /> Go to account
        </a>
      </div>

      <div
        style={{
          color: "#6b6b6b",
          fontSize: "0.9rem",
          marginTop: "10px",
        }}
      >
        Need help? We're on{" "}
        <a href={discordInviteUrl} target="_blank">
          discord
        </a>
        .
      </div>
    </div>
  );
}
