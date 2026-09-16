import type { LinksFunction } from "@remix-run/node";
import { useFetchers, useNavigation } from "@remix-run/react";
import NProgress from "nprogress";
import nProgressStyles from "nprogress/nprogress.css";
import { useEffect } from "react";
import { silentSubmitKey } from "~/consts";

export const globalProgressStyles: LinksFunction = () => {
  return [{ rel: "stylesheet", href: nProgressStyles }];
};

const parent = "body";

export const useGlobalProgress = () => {
  const navigation = useNavigation();
  const fetchers = useFetchers();

  // Submits the user did not ask for - a realtime refresh, persisting whether the nav rail is
  // collapsed - tag their body so they fetch without spinning. The bar means "the page you
  // asked for is on its way"; it should not fire for the app talking to itself.
  const isSilent = navigation.json?.hasOwnProperty(silentSubmitKey);

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
        if (isSilent) break;
        if (!NProgress.isStarted()) {
          NProgress.start();
        }
        NProgress.set(0.3);
        break;
      case "loading":
        if (isSilent) break;
        if (!NProgress.isStarted()) {
          NProgress.start();
        }
        NProgress.set(typeof navigation.formAction === "undefined" ? 0.3 : 0.7);
        break;
    }
  }, [fetchers, navigation.formAction, isSilent, navigation.state]);
};
