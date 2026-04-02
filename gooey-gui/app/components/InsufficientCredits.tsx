type InsufficientCreditsProps = {
  accountUrl: string;
  discordInviteUrl: string;
  isAnonymous: boolean;
  verifiedEmailUserFreeCredits: number;
};

export function InsufficientCredits({
  accountUrl,
  discordInviteUrl,
  isAnonymous,
  verifiedEmailUserFreeCredits,
}: InsufficientCreditsProps) {
  return (
    <div
      style={{
        background: "#f0fdf4",
        border: "1px solid rgba(22, 163, 74, 0.2)",
        borderLeft: "6px solid #16a34a",
        borderRadius: "12px",
        maxWidth: "560px",
        padding: "16px 18px",
      }}
    >
      {isAnonymous ? (
        <>
          <p
            style={{ color: "#14532d", fontSize: "0.98rem", marginTop: 0 }}
            data-submitafterlogin
          >
            Doh!{" "}
            <a href={accountUrl} target="_top">
              Please login
            </a>{" "}
            to run more Gooey.AI workflows.
          </p>

          <p
            style={{
              color: "#166534",
              fontSize: "0.95rem",
              marginBottom: 0,
              marginTop: "10px",
            }}
          >
            You will receive {verifiedEmailUserFreeCredits} Credits when you
            sign up via your phone #, Google, Apple or GitHub account and can{" "}
            <a href="/pricing/" target="_blank">
              purchase more
            </a>{" "}
            for $1/100 Credits.
          </p>
        </>
      ) : (
        <>
          <p style={{ color: "#14532d", fontSize: "0.98rem", marginTop: 0 }}>
            Doh! You're out of Gooey.AI credits.
          </p>

          <p
            style={{ color: "#14532d", fontSize: "0.98rem", marginTop: "10px" }}
          >
            Please{" "}
            <a href={accountUrl} target="_blank">
              buy more
            </a>{" "}
            to run more workflows.
          </p>

          <p
            style={{
              color: "#166534",
              fontSize: "0.9rem",
              marginBottom: 0,
              marginTop: "10px",
            }}
          >
            We are always on{" "}
            <a href={discordInviteUrl} target="_blank">
              discord
            </a>{" "}
            if you have any questions.
          </p>
        </>
      )}
    </div>
  );
}
