import path from "path";

export function urlToFilename(_url: string) {
  const url = new URL(_url);
  if (isUserUploadedUrl(_url)) {
    return decodeURIComponent(path.basename(url.pathname));
  } else {
    return `${url.hostname}${url.pathname}${url.search}`;
  }
}

export function isUserUploadedUrl(url: string) {
  return (
    url.includes(`storage.googleapis.com`) && url.includes(`daras_ai/media`)
  );
}
