import { LinksFunction } from "@remix-run/node";

import audioStyle from "@uppy/audio/dist/style.min.css";
import coreStyle from "@uppy/core/dist/style.min.css";
import dashboardStyle from "@uppy/dashboard/dist/style.min.css";
import webcamStyle from "@uppy/webcam/dist/style.min.css";

export const links: LinksFunction = () => {
  return [
    { rel: "stylesheet", href: coreStyle },
    { rel: "stylesheet", href: dashboardStyle },
    { rel: "stylesheet", href: webcamStyle },
    { rel: "stylesheet", href: audioStyle },
  ];
};
