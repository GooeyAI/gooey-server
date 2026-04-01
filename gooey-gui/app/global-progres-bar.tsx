import type { LinksFunction } from "@remix-run/node";
import { useFetchers, useNavigation } from "@remix-run/react";
import NProgress from "nprogress";
import nProgressStyles from "nprogress/nprogress.css";
import { useEffect } from "react";

export const globalProgressStyles: LinksFunction = () => {
  return [{ rel: "stylesheet", href: nProgressStyles }];
};

const parent = "body";

export const useGlobalProgress = () => {
  const navigation = useNavigation();
  const fetchers = useFetchers();

  useEffect(() => {
    if (!document.querySelector(parent)) return;
    NProgress.configure({ parent, trickleSpeed: 100 });
  }, []);

  useEffect(() => {
    if (!document.querySelector(parent)) return;
    switch (navigation.state) {
      case "idle":
        NProgress.done();
        break;
      case "submitting":
        if (!NProgress.isStarted()) {
          NProgress.start();
        }
        NProgress.set(0.3);
        break;
      case "loading":
        if (!NProgress.isStarted()) {
          NProgress.start();
        }
        NProgress.set(typeof navigation.formAction === "undefined" ? 0.3 : 0.7);
        break;
    }
  }, [fetchers, navigation.formAction, navigation.state]);
};
