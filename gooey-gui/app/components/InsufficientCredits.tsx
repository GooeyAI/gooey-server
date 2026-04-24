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
      className={`btn btn-theme p-2 m-0 btn-${variant}`}
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
    <div className="insufficient-credits__subtext">
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
    <div className="insufficient-credits__title">
      <span className="insufficient-credits__icon">
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
      <div className="insufficient-credits" data-submitafterlogin>
        <Title>{title}</Title>
        <div className="insufficient-credits__body">
          Doh! <a href={accountUrl} target="_top">Please login</a> to run more
          Gooey.AI workflows.
        </div>
        <div className="insufficient-credits__subtext">
          You will receive {verifiedEmailUserFreeCredits} Credits when you sign
          up via your phone #, Google, Apple or GitHub account and can{" "}
          <a href="/pricing/" target="_blank">purchase more</a> for $1/100 Credits.
        </div>
      </div>
    );
  }

  return (
    <div className="insufficient-credits">
      <Title>{title}</Title>
      <CostLine
        price={price}
        workspaceName={rerunWorkspaceName}
        workspaceBalance={rerunWorkspaceBalance}
      />
      <div className="insufficient-credits__actions">
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
