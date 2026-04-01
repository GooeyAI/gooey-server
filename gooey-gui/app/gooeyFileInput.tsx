import Audio from "@uppy/audio";
import type { UppyFile } from "@uppy/core";
import Uppy from "@uppy/core";
import { Dashboard } from "@uppy/react";
import Url from "@uppy/url";
import Webcam from "@uppy/webcam";
import XHR from "@uppy/xhr-upload";
import mime from "mime-types";
import { useEffect, useRef, useState } from "react";
import type { TooltipPlacement } from "./components/GooeyTooltip";
import { InputLabel } from "./gooeyInput";
import { urlToFilename } from "./urlUtils";
import { useGlobalContext } from "./globalContext";

export function GooeyFileInput({
  name,
  label,
  accept,
  multiple,
  defaultValue,
  uploadMeta,
  help,
  tooltipPlacement,
}: {
  name: string;
  label: string;
  accept: string[] | undefined;
  multiple: boolean;
  defaultValue: string | string[] | undefined;
  uploadMeta: Record<string, string>;
  help?: string;
  tooltipPlacement?: TooltipPlacement;
}) {
  const [uppy, setUppy] = useState<Uppy | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState(defaultValue);
  const [showClearAll, setShowClearAll] = useState(false);
  const ctx = useGlobalContext();
  const state = ctx.current.session_state;

  // if the server value changes, update the uppy state
  useEffect(() => {
    if (uppy && value && JSON.stringify(value) != JSON.stringify(state[name])) {
      setShowClearAll(loadUppyFiles(state[name] || [], uppy));
      setValue(state[name]);
    }
  }, [name, state[name]]);

  useEffect(() => {
    let _uppy = initializeUppy({
      name,
      accept,
      multiple,
      uploadMeta,
      defaultValue,
      setShowClearAll,
      setValue(value) {
        setValue(value);
        inputRef.current!.value = JSON.stringify(value) || "";
        ctx.current.rerun();
      },
    });
    setUppy(_uppy);
    return () => {
      _uppy.close();
    };
  }, []);

  return (
    <div className="gui-input">
      <input
        hidden
        ref={inputRef}
        name={name}
        value={JSON.stringify(value) || ""}
        readOnly
      />
      <InputLabel
        label={label}
        help={help}
        tooltipPlacement={tooltipPlacement}
      />
      {uppy ? (
        <div className="w-100 position-relative" style={{ zIndex: 0 }}>
          <Dashboard
            showRemoveButtonAfterComplete
            showLinkToFileUploadResult
            hideUploadButton
            uppy={uppy}
            height={258}
            width={"100%"}
            singleFileFullScreen={false}
            plugins={["Url", "Webcam", "Audio"]}
            // @ts-ignore
            doneButtonHandler={null}
          />
          {showClearAll ? (
            <button
              className="uppy-Dashboard--clear-all"
              role="button"
              onClick={() => uppy.cancelAll()}
            >
              🗑 Clear All
            </button>
          ) : null}
        </div>
      ) : (
        "Loading..."
      )}
    </div>
  );
}

function initializeUppy({
  name,
  accept,
  multiple,
  uploadMeta,
  defaultValue,
  setShowClearAll,
  setValue,
}: {
  name: string;
  accept: string[] | undefined;
  multiple: boolean;
  uploadMeta: Record<string, string>;
  defaultValue: string | string[] | undefined;
  setShowClearAll: (value: boolean) => void;
  setValue: (value: string | string[]) => void;
}): Uppy {
  function onFilesChanged() {
    if (!_uppy || !_uppy.getState().initDone) return;
    const uploadUrls = _uppy
      .getFiles()
      .map((file: any) => file.uploadURL)
      .filter((url) => url);
    setShowClearAll(
      uploadUrls.length > 0 && _uppy.getState().totalProgress >= 100
    );
    setValue(multiple ? uploadUrls : uploadUrls[0]);
  }

  function onFileUploaded(file: any) {
    if (!_uppy || !_uppy.getState().initDone) return;
    onFilesChanged();
    file = _uppy.getFile(file.id); // for some reason, the file object is not the same as the one in the uppy state
    loadPreview({
      url: file.uploadURL,
      uppy: _uppy,
      fileId: file.id,
      filename: file.name,
      preview: file.preview,
    });
  }

  function onFileAdded(file: UppyFile) {
    if (!_uppy || !_uppy.getState().initDone) return;
    if (file.source != "Url") {
      setShowClearAll(false);
      return;
    }
    const url = file?.remote?.body?.url?.toString();
    if (!url) return;
    _uppy.setFileState(file.id, {
      progress: {
        uploadComplete: true,
        uploadStarted: true,
        percentage: 100,
        bytesUploaded: file.data.size,
      },
      uploadURL: url,
    });
    _uppy.setFileMeta(file.id, {
      name: urlToFilename(url),
    });
    (_uppy as any).calculateTotalProgress();
    onFilesChanged();
    loadPreview({
      url: url,
      uppy: _uppy,
      fileId: file.id,
      filename: file.name,
      preview: file.preview,
    });
  }

  let _uppy: Uppy = new Uppy({
    id: name,
    allowMultipleUploadBatches: true,
    restrictions: {
      maxFileSize: 250 * 1024 * 1024,
      maxNumberOfFiles: multiple ? 500 : 1,
      allowedFileTypes: accept ? accept.concat(["url/undefined"]) : undefined,
    },
    locale: {
      strings: {
        uploadComplete: "",
        complete: "Uploaded",
      },
    },
    meta: uploadMeta,
    autoProceed: true,
  })
    .use(Url, { companionUrl: "/__/file-upload/" })
    .use(XHR, {
      endpoint: "/__/file-upload/",
      shouldRetry(xhr: XMLHttpRequest) {
        return [408, 429, 502, 503].includes(xhr.status);
      },
    })
    .on("file-added", onFileAdded)
    .on("upload-success", onFileUploaded)
    .on("file-removed", onFilesChanged);

  // only enable relevant plugins
  if (
    !accept ||
    accept.some(
      (a) => a.startsWith("image") || a.startsWith("video") || a.startsWith("*")
    )
  ) {
    _uppy.use(Webcam);
  }
  if (
    !accept ||
    accept.some((a) => a.startsWith("audio") || a.startsWith("*"))
  ) {
    _uppy.use(Audio);
  }

  setShowClearAll(loadUppyFiles(defaultValue, _uppy));

  return _uppy;
}

function loadUppyFiles(
  defaultValue: string | string[] | undefined,
  uppy: Uppy
): boolean {
  uppy.setState({ initDone: false });
  for (const file of uppy.getFiles()) {
    uppy.removeFile(file.id);
  }
  let urls = defaultValue;
  if (typeof urls === "string") {
    urls = [urls];
  }
  urls ||= [];
  for (let url of urls) {
    let filename;
    try {
      filename = urlToFilename(url);
    } catch (e) {
      continue;
    }
    const contentType = mime.lookup(filename) || "url/undefined";
    const preview = contentType?.startsWith("image/") ? url : undefined;
    let fileId;
    try {
      fileId = uppy.addFile({
        name: filename,
        type: contentType,
        data: new Blob(),
        preview: preview,
        meta: {
          relativePath: new Date().toISOString(), // this is a hack to make the file unique
        },
      });
    } catch (e) {
      console.error(e);
      continue;
    }
    uppy.setFileState(fileId, {
      progress: { uploadComplete: true, uploadStarted: true, percentage: 100 },
      uploadURL: url,
      size: undefined,
    });
    loadPreview({ url, uppy, fileId, filename, preview });
  }
  const hasFiles = uppy.getFiles().length > 0;
  if (hasFiles) {
    uppy.setState({ totalProgress: 100 });
  }
  uppy.setState({ initDone: true });
  return hasFiles;
}

const metascraperUrl = "https://metascraper.gooey.ai/fetchUrlMeta";

async function loadPreview({
  url,
  uppy,
  fileId,
  filename,
  preview,
}: {
  url: string;
  uppy: Uppy;
  fileId: string;
  filename?: string;
  preview?: string;
}) {
  if (uppy.getFile(fileId).meta.type?.startsWith("image/")) return;

  let contentType, contentLength;
  try {
    let response = await fetch(url);
    if (response.ok) {
      contentType = response.headers.get("content-type") || "url/undefined";
      contentLength = response.headers.get("content-length");
    }
  } catch (e) {
    console.log("failed to HEAD:", url, e);
  }

  // if the content type is an image, show the image itself
  if (contentType?.startsWith("image/")) {
    preview = url;
  }
  // if its a webpage, then fetch the meta data
  else if (!contentType || contentType.startsWith("text/html")) {
    let apiUrl = new URL(metascraperUrl);
    apiUrl.search = new URLSearchParams({ url }).toString();

    let response = await fetch(apiUrl);
    let data = await response.json();
    let { content_type, image, logo, title } = data;

    contentType = content_type;
    preview = preview || image || logo;

    if (!uppy.getFile(fileId)) return;
    if (title) {
      uppy.setFileMeta(fileId, {
        name: title,
      });
    }
  }

  uppy.setFileState(fileId, {
    size: contentLength ? parseInt(contentLength) : undefined,
    preview: preview,
  });
}
