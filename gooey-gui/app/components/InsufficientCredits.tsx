type InsufficientCreditsProps = {
  accountUrl: string;
  isAnonymous: boolean;
  verifiedEmailUserFreeCredits: number;
  rerunKey: string;
  upgradeKey: string;
  buyCreditsKey: string;
  price: number | null;
  title: string;
  showUpgrade: boolean;
  showRerun: boolean;
  rerunWorkspaceName: string | null;
  rerunWorkspaceBalance: number | null;
};

const containerStyle: React.CSSProperties = {
  background: "#fff7e8",
  border: "1px solid rgba(198, 144, 0, 0.35)",
  borderLeft: "6px solid #c69000",
  borderRadius: "10px",
  maxWidth: "560px",
  padding: "16px 18px",
};

const iconBadgeStyle: React.CSSProperties = {
  alignItems: "center",
  background: "#fff1cf",
  borderRadius: "8px",
  color: "#9c6b00",
  display: "inline-flex",
  height: "28px",
  justifyContent: "center",
  width: "28px",
};

const titleRowStyle: React.CSSProperties = {
  alignItems: "center",
  color: "#2a2a2a",
  display: "flex",
  fontSize: "1.05rem",
  fontWeight: 600,
  gap: "10px",
};

const bodyTextStyle: React.CSSProperties = {
  color: "#4a4a4a",
  fontSize: "0.98rem",
  marginTop: "8px",
};

const subTextStyle: React.CSSProperties = {
  color: "#6b6b6b",
  fontSize: "0.9rem",
  marginTop: "8px",
};

const actionsRowStyle: React.CSSProperties = {
  marginTop: "6px",
  display: "flex",
  gap: "8px",
  flexWrap: "wrap",
};

const BTN_CLASS = "btn btn-theme p-2 m-0";

function SubmitKeyBtn({
  name,
  label,
  variant = "primary",
}: {
  name: string;
  label: string;
  variant?: "primary" | "secondary";
}) {
  return (
    <button
      type="submit"
      name={name}
      value="1"
      className={`${BTN_CLASS} btn-${variant}`}
    >
      {label}
    </button>
  );
}

function CostLine({
  price,
  workspaceName,
  workspaceBalance,
}: {
  price: number | null;
  workspaceName: string | null;
  workspaceBalance: number | null;
}) {
  return (
    <div style={subTextStyle}>
      This run will cost{" "}
      <strong>{price ? `${price} Cr` : ">1 Cr"}</strong> and your current{" "}
      <strong>{workspaceName}</strong> balance is{" "}
      <strong>
        {workspaceBalance != null ? workspaceBalance.toLocaleString() : "—"}
      </strong>
      .
    </div>
  );
}

function Title({ children }: { children: React.ReactNode }) {
  return (
    <div style={titleRowStyle}>
      <span style={iconBadgeStyle}>
        <i className="fa-regular fa-coin" />
      </span>
      <span>{children}</span>
    </div>
  );
}

export function InsufficientCredits({
  accountUrl,
  isAnonymous,
  verifiedEmailUserFreeCredits,
  rerunKey,
  upgradeKey,
  buyCreditsKey,
  price,
  title,
  showUpgrade,
  showRerun,
  rerunWorkspaceName,
  rerunWorkspaceBalance,
}: InsufficientCreditsProps) {
  if (isAnonymous) {
    return (
      <div style={containerStyle} data-submitafterlogin>
        <Title>{title}</Title>
        <div style={bodyTextStyle}>
          Doh! <a href={accountUrl} target="_top">Please login</a> to run more
          Gooey.AI workflows.
        </div>
        <div style={subTextStyle}>
          You will receive {verifiedEmailUserFreeCredits} Credits when you sign
          up via your phone #, Google, Apple or GitHub account and can{" "}
          <a href="/pricing/" target="_blank">purchase more</a> for $1/100 Credits.
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <Title>{title}</Title>
      <CostLine
        price={price}
        workspaceName={rerunWorkspaceName}
        workspaceBalance={rerunWorkspaceBalance}
      />
      <div style={actionsRowStyle}>
        {showUpgrade && (
          <SubmitKeyBtn
            name={upgradeKey}
            label="Upgrade Team"
          />
        )}
        {showRerun ? (
          <SubmitKeyBtn
            name={rerunKey}
            label={`Re-run in ${rerunWorkspaceName}`}
            variant={showUpgrade ? "secondary" : "primary"}
          />
        ) : (
          <SubmitKeyBtn
            name={buyCreditsKey}
            label={`Buy ${rerunWorkspaceName} Credits`}
            variant={showUpgrade ? "secondary" : "primary"}
          />
        )}
      </div>
    </div>
  );
}
