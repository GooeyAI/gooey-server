type LanguagePageProps = {
  language: string;
  languageTag: string;
  newRunUrl: string;
};

const quickPoints = [
  "Upload audio or video",
  "Compare supported ASR models",
  "Translate the transcript if needed",
];

export function LanguagePage({
  language,
  languageTag,
  newRunUrl,
}: LanguagePageProps) {
  return (
    <section
      style={{
        background:
          "linear-gradient(180deg, rgba(255, 249, 238, 0.96) 0%, rgba(255, 255, 255, 1) 18rem)",
        border: "1px solid rgba(17, 24, 39, 0.06)",
        borderRadius: "28px",
        boxShadow: "0 18px 46px rgba(17, 24, 39, 0.05)",
        margin: "52px auto 16px",
        maxWidth: "980px",
        overflow: "hidden",
        padding: "34px 34px 30px",
        position: "relative",
      }}
    >
      <div
        style={{
          background:
            "radial-gradient(circle at top right, rgba(255, 218, 107, 0.24), transparent 32%), radial-gradient(circle at 18% 82%, rgba(189, 224, 254, 0.28), transparent 28%)",
          inset: 0,
          pointerEvents: "none",
          position: "absolute",
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "26px",
          position: "relative",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "18px",
          }}
        >
          <div
            style={{
              alignItems: "center",
              display: "flex",
              flexWrap: "wrap",
              gap: "10px",
            }}
          >
            <span
              style={{
                background: "#111827",
                borderRadius: "999px",
                color: "#ffffff",
                display: "inline-flex",
                fontSize: "0.78rem",
                fontWeight: 700,
                letterSpacing: "0.1em",
                padding: "7px 12px",
                textTransform: "uppercase",
              }}
            >
              {languageTag}
            </span>
            <span
              style={{
                color: "#8a5a00",
                fontSize: "0.88rem",
                fontWeight: 600,
                letterSpacing: "0.03em",
                textTransform: "uppercase",
              }}
            >
              Global language understanding for AI
            </span>
          </div>

          <div>
            <h1
              style={{
                color: "#111827",
                fontSize: "clamp(2.35rem, 5vw, 4.25rem)",
                lineHeight: 0.92,
                margin: 0,
                maxWidth: "12ch",
              }}
            >
              Understand {language} audio with Gooey.AI
            </h1>
            <p
              style={{
                color: "#4b5563",
                fontSize: "1.12rem",
                lineHeight: 1.55,
                margin: "16px 0 0 0",
                maxWidth: "47rem",
              }}
            >
              Inspired by Gooey.AI&apos;s work on language evaluation and
              multilingual AI, this page opens speech recognition with{" "}
              {language} already selected so you can move straight to your
              audio, your model choice, and your transcript.
            </p>
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <a
              href={newRunUrl}
              className="btn btn-theme btn-primary p-2 m-0"
              style={{
                borderRadius: "16px",
                boxShadow: "0 12px 24px rgba(0, 0, 0, 0.14)",
                paddingLeft: "18px",
                paddingRight: "18px",
                textDecoration: "none",
              }}
            >
              <i className="fa-solid fa-microphone-lines" /> Start a new ASR run
            </a>
            <div
              style={{
                alignItems: "center",
                color: "#6b7280",
                display: "inline-flex",
                fontSize: "0.94rem",
                minHeight: "46px",
              }}
            >
              Nothing is submitted until you upload audio and press Run.
            </div>
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gap: "14px",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          }}
        >
          <div
            style={{
              background: "rgba(255, 255, 255, 0.8)",
              border: "1px solid rgba(17, 24, 39, 0.08)",
              borderRadius: "18px",
              minHeight: "100%",
              padding: "18px",
            }}
          >
            <div
              style={{
                color: "#111827",
                fontSize: "0.92rem",
                fontWeight: 700,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}
            >
              Built for real language coverage
            </div>
            <div
              style={{
                color: "#4b5563",
                fontSize: "0.98rem",
                lineHeight: 1.55,
                marginTop: "10px",
              }}
            >
              Gooey.AI supports a large set of spoken languages across multiple
              ASR engines, including many underrepresented and low-resource
              language scenarios.
            </div>
          </div>

          <div
            style={{
              background: "rgba(255, 255, 255, 0.8)",
              border: "1px solid rgba(17, 24, 39, 0.08)",
              borderRadius: "18px",
              minHeight: "100%",
              padding: "18px",
            }}
          >
            <div
              style={{
                color: "#111827",
                fontSize: "0.92rem",
                fontWeight: 700,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}
            >
              In the workflow
            </div>
            <div
              style={{
                color: "#4b5563",
                fontSize: "0.98rem",
                lineHeight: 1.55,
                marginTop: "10px",
              }}
            >
              {quickPoints.join(". ")}.
            </div>
          </div>

          <div
            style={{
              background: "#111827",
              borderRadius: "18px",
              color: "#f9fafb",
              minHeight: "100%",
              padding: "18px",
            }}
          >
            <div
              style={{
                fontSize: "0.92rem",
                fontWeight: 700,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}
            >
              Quick start
            </div>
            <div
              style={{
                color: "rgba(249, 250, 251, 0.84)",
                fontSize: "0.98rem",
                lineHeight: 1.55,
                marginTop: "10px",
              }}
            >
              Language preset: <strong>{language}</strong> ({languageTag})
            </div>
            <div
              style={{
                color: "rgba(249, 250, 251, 0.84)",
                fontSize: "0.98rem",
                lineHeight: 1.55,
                marginTop: "10px",
              }}
            >
              The button above opens Gooey.AI&apos;s ASR workflow with this
              language already configured.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
