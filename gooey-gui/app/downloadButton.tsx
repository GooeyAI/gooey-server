import React from "react";
import { RenderedMarkdown } from "~/renderedMarkdown";
import { urlToFilename } from "./urlUtils";

export function DownloadButton({
  label,
  className,
  url,
  ...props
}: {
  label: string;
  className?: string;
  url: string;
}) {
  const [isDownloading, setIsDownloading] = React.useState(false);
  return (
    <div
      className={`btn btn-theme ${className ?? ""}`}
      {...props}
      onClick={async () => {
        if (isDownloading) return;
        setIsDownloading(true);
        try {
          await download(url);
        } finally {
          setIsDownloading(false);
        }
      }}
    >
      <div style={isDownloading ? { opacity: 0.3, position: "relative" } : {}}>
        {isDownloading ? (
          <div
            style={{
              position: "absolute",
              width: "100%",
              height: "100%",
              top: "-5px",
            }}
          >
            <div className="gooey-spinner"></div>
          </div>
        ) : null}
        <RenderedMarkdown body={label} />
      </div>
    </div>
  );
}

async function download(url: string) {
  let response = await fetch(url);
  let blob = await response.blob();
  let a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = urlToFilename(url);
  a.onclick = (e) => {
    e.stopPropagation();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 250);
  };
  a.click();
}
