import { LinksFunction } from "@remix-run/node";
import tippyAnimStyles from "tippy.js/animations/scale.css";

export const links: LinksFunction = () => {
  return [{ rel: "stylesheet", href: tippyAnimStyles }];
};
