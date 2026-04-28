import { useEffect, useState } from "react";
import { RenderedMarkdown } from "~/renderedMarkdown";
import { Link } from "@remix-run/react";

export function GooeyImg({
  src,
  caption,
  href,
  previewImg,
  ...props
}: {
  src: string;
  caption?: string;
  href?: string;
  previewImg?: string;
}) {
  const [previewIsValid, onError] = useImageValid(previewImg);

  let currentSrc;
  if (previewImg && previewIsValid) {
    currentSrc = previewImg;
  } else {
    currentSrc = src;
  }

  let child = (
    <>
      <RenderedMarkdown body={caption} />
      <img
        className="gui-img"
        alt={caption}
        src={currentSrc}
        onError={onError}
        {...props}
        // onClick={() => {
        //   if (href || currentSrc.startsWith("data:")) return;
        //   window.open(currentSrc);
        // }}
      />
    </>
  );

  if (href) {
    child = (
      <Link to={href}>
        <div>{child}</div>
      </Link>
    );
  }

  return child;
}

export function GooeyVideo({
  src,
  caption,
  previewImg,
  ...props
}: {
  src: string;
  caption?: string;
  previewImg?: string;
}) {
  const [previewIsValid, onError] = useImageValid(previewImg);

  let child;
  if (previewImg && previewIsValid) {
    child = (
      <img
        className="gui-video"
        src={previewImg}
        alt={caption}
        onError={onError}
      />
    );
  } else {
    child = <video className="gui-video" {...props} src={src}></video>;
  }

  return (
    <>
      <RenderedMarkdown body={caption} />
      {child}
    </>
  );
}

/**
 * Validates an image URL by loading it through a fresh `Image` element so the
 * `load`/`error` handlers are guaranteed to be attached before the request
 * starts. This sidesteps the React SSR hydration race documented at
 * https://github.com/facebook/react/issues/15446 (where `onError` on a
 * server-rendered `<img>` can fire before React hydrates and is dropped).
 *
 * Adapted from `react-component/image` (used by ant-design):
 * https://github.com/react-component/image/blob/master/src/util.ts
 */
function useImageValid(src?: string): [boolean, () => void] {
  const [isValid, setIsValid] = useState(true);

  useEffect(() => {
    if (!src) return;
    // Optimistically assume the new src is valid so we don't waste bandwidth
    // fetching the full asset while parallel validation runs.
    setIsValid(true);

    let ignore = false;
    let img = new Image();
    img.onload = () => {
      if (!ignore) setIsValid(true);
    };
    img.onerror = () => {
      if (!ignore) setIsValid(false);
    };
    img.src = src;

    return () => {
      ignore = true;
    };
  }, [src]);

  return [isValid, () => setIsValid(false)];
}
