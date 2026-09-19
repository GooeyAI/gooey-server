import { useState } from "react";

/** How long the "Link copied" acknowledgement stays up. */
const COPIED_RESET_MS = 2000;

/** Copy a url, falling back to a prompt the user can copy out of by hand - there is no
 *  clipboard in an insecure context, and writing to it can be refused outright.
 *
 *  `copied` drives the acknowledgement and clears itself. */
export function useCopyToClipboard(resetMs: number = COPIED_RESET_MS) {
  const [copied, setCopied] = useState(false);
  const copyUrl = (url: string) => {
    if (!navigator.clipboard) {
      window.prompt("Copy this link", url);
      return;
    }
    navigator.clipboard
      .writeText(url)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), resetMs);
      })
      .catch(() => window.prompt("Copy this link", url));
  };
  return { copied, copyUrl };
}
