import { GooeyImg, GooeyVideo } from "~/components/MediaTags";
import { RenderedMarkdown } from "~/renderedMarkdown";
import { LineClamp } from "~/renderedHTML";
import type { CardPreview } from "./types";

export function PreviewContent({ preview }: { preview: CardPreview }) {
  switch (preview.type) {
    case "chat":
      return (
        <div className="d-flex flex-column justify-content-center gap-3 p-3 h-100">
          {preview.userMessage && (
            <div className="d-flex justify-content-end">
              <div className="recent-card-chat-bubble border rounded-3 px-2 py-1 text-break">
                <LineClamp lines={2} expandable={false}>
                  {preview.userMessage}
                </LineClamp>
              </div>
            </div>
          )}
          {preview.botMessage && (
            <div className="d-flex justify-content-start">
              <div className="recent-card-chat-bubble bg-white rounded-3 px-2 py-1 text-break line-clamp-3 container-margin-reset">
                <RenderedMarkdown
                  body={preview.botMessage}
                  lineClamp={3}
                  lineClampExpand={false}
                />
              </div>
            </div>
          )}
        </div>
      );
    case "image":
      return (
        <GooeyImg
          src={preview.url}
          previewImg={preview.previewImg ?? undefined}
        />
      );
    case "video":
      return (
        <GooeyVideo
          src={preview.url}
          previewImg={preview.previewImg ?? undefined}
          muted
          playsInline
          preload="metadata"
          autoPlay
          loop
        />
      );
    case "audio":
      return (
        <div className="d-flex flex-column justify-content-center h-100 px-3">
          <audio src={preview.url} controls className="w-100" />
          {preview.caption && (
            <div className="text-muted small mt-2 text-break line-clamp-2">
              {preview.caption}
            </div>
          )}
        </div>
      );
    case "icon":
      return (
        <div className="d-flex align-items-center justify-content-center h-100 text-muted">
          {preview.imageUrl ? (
            <img
              src={preview.imageUrl}
              alt=""
              className="recent-card-icon-img"
            />
          ) : preview.emoji ? (
            <span className="recent-card-icon-emoji">{preview.emoji}</span>
          ) : null}
        </div>
      );
  }
}
