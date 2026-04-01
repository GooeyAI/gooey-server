import { withSentry } from "@sentry/remix";
import { FormEvent, useEffect, useRef } from "react";

import { json, LinksFunction, redirect } from "@remix-run/node";
import type {
  ShouldRevalidateFunction,
  SubmitOptions,
  V2_MetaFunction,
} from "@remix-run/react";
import {
  useActionData,
  useFetcher,
  useLoaderData,
  useNavigate,
  useSearchParams,
  useSubmit,
} from "@remix-run/react";
import path from "path";
import { useDebouncedCallback } from "use-debounce";
import { useEventSourceNullOk } from "~/event-source";
import { handleRedirectResponse } from "~/handleRedirect";
import { applyFormDataTransforms, RenderedChildren } from "~/renderer";

import { gooeyGuiRouteHeader } from "~/consts";
import appStyles from "~/styles/app.css";
import customStyles from "~/styles/custom.css";
import { GlobalContextProvider } from "./globalContext";
import settings from "./settings";

export const meta: V2_MetaFunction = ({ data }) => {
  return data.meta ?? [];
};

export const links: LinksFunction = () => {
  return [
    {
      rel: "stylesheet",
      href: "https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css",
      integrity:
        "sha384-rbsA2VBKQhggwzxH7pPCaAqO46MgnOM80zW1RWuH61DGLwZJEdK2Kadq2F9CUG65",
      crossOrigin: "anonymous",
    },
    {
      rel: "stylesheet",
      href: "https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css",
      crossOrigin: "anonymous",
      referrerPolicy: "no-referrer",
    },
    {
      rel: "stylesheet",
      href: "https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/toolbar/prism-toolbar.min.css",
      crossOrigin: "anonymous",
      referrerPolicy: "no-referrer",
    },
    ...require("~/gooeyFileInput.styles").links(),
    ...require("~/components/GooeyPopover.styles").links(),
    { rel: "stylesheet", href: customStyles },
    { rel: "stylesheet", href: appStyles },
  ];
};

export async function loader({ request }: { request: Request }) {
  const requestUrl = new URL(request.url);
  const serverUrl = new URL(settings.SERVER_HOST!);
  serverUrl.pathname = path.join(serverUrl.pathname, requestUrl.pathname ?? "");
  serverUrl.search = requestUrl.search;

  request.headers.delete("Host");
  request.headers.set(gooeyGuiRouteHeader, "1");

  let body;
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
    body = await request.arrayBuffer();
  }

  let response = await fetch(serverUrl, {
    method: request.method,
    redirect: "manual",
    body,
    headers: request.headers,
  });

  const redirectUrl = handleRedirectResponse({ response });
  if (redirectUrl) {
    return redirect(redirectUrl, {
      headers: response.headers,
      status: response.status,
      statusText: response.statusText,
    });
  }

  if (response.headers.get(gooeyGuiRouteHeader)) {
    return response;
  } else {
    return json({
      base64Body: Buffer.from(await response.arrayBuffer()).toString("base64"),
      headers: Object.fromEntries(response.headers),
      status: response.status,
      statusText: response.statusText,
    });
  }
}

export const action = loader;

export const shouldRevalidate: ShouldRevalidateFunction = (args) => {
  if (
    // don't revalidate if its a form submit with successful response
    args.actionResult &&
    args.formMethod === "POST" &&
    args.currentUrl.toString() === args.nextUrl.toString()
  ) {
    return false;
  }
  if (typeof window !== "undefined") {
    // @ts-ignore
    window.hydrated = false;
  }
  return args.defaultShouldRevalidate;
};

function useRealtimeChannels({
  channels,
}: {
  channels: string[] | undefined | null;
}) {
  let url;
  if (channels && channels.length) {
    const params = new URLSearchParams(
      channels.map((name) => ["channels", name])
    );
    url = `/__/realtime/?${params}`;
  }
  return useEventSourceNullOk(url);
}

export type OnChange = (event?: {
  target: EventTarget | HTMLElement | null | undefined;
  currentTarget?: EventTarget | HTMLElement | null | undefined;
}) => void;

function base64Decode(base64EncodedString: string): string {
  return new TextDecoder().decode(
    Uint8Array.from(atob(base64EncodedString), (m) => m.charCodeAt(0))
  );
}

function App() {
  const [searchParams] = useSearchParams();
  const loaderData = useLoaderData<typeof loader>();
  const actionData = useActionData<typeof action>();
  const { base64Body, children, state, channels } = actionData ?? loaderData;
  const formRef = useRef<HTMLFormElement>(null);
  const realtimeEvent = useRealtimeChannels({ channels });
  const fetcher = useFetcher();
  const submit = useSubmit();
  const navigate = useNavigate();

  useEffect(() => {
    if (!base64Body) return;
    let body = base64Decode(base64Body);
    let frag = document.createRange().createContextualFragment(body);
    document.documentElement.innerHTML = "";
    document.documentElement.appendChild(frag);
  }, [base64Body]);

  useEffect(() => {
    if (realtimeEvent && fetcher.state === "idle" && formRef.current) {
      onSubmit();
    }
  }, [fetcher.state, realtimeEvent, submit]);

  const onChange: OnChange = (event) => {
    const target = event?.target;
    const form = event?.currentTarget || formRef?.current;
    if (!(form && form instanceof HTMLFormElement)) return;

    // ignore elements that have `data-submit-disabled` set
    if (
      target instanceof HTMLElement &&
      target.hasAttribute("data-submit-disabled")
    ) {
      return;
    }

    // debounce based on input type - generally text inputs are slow, everything else is fast
    if (
      (target instanceof HTMLInputElement && target.type === "text") ||
      target instanceof HTMLTextAreaElement
    ) {
      form.setAttribute("debounceInProgress", "true");
      debouncedSubmit(form);
    } else if (
      target instanceof HTMLInputElement &&
      target.type === "number" &&
      document.activeElement === target
    ) {
      // number inputs have annoying limits and step sizes that make them hard to edit unless we postpone autocorrection until focusout
      // debounce does not work here because the step size prevents key intermediate states while typing
      if (form.getAttribute("debounceInProgress") == "true") return;
      form.setAttribute("debounceInProgress", "true");
      target.addEventListener(
        "focusout",
        function () {
          form.removeAttribute("debounceInProgress");
          onSubmit();
        },
        { once: true }
      );
    } else {
      onSubmit();
    }
  };

  const debouncedSubmit = useDebouncedCallback((form: HTMLFormElement) => {
    form.removeAttribute("debounceInProgress");
    onSubmit();
  }, 500);

  let submitOptions: SubmitOptions = {
    method: "post",
    action: "?" + searchParams,
    encType: "application/json",
  };

  const onSubmit = (event?: FormEvent) => {
    if (!formRef.current) return;
    let formData = Object.fromEntries(new FormData(formRef.current));
    if (event) {
      event.preventDefault();
      let submitter = (event.nativeEvent as SubmitEvent)
        .submitter as HTMLFormElement;
      if (submitter) {
        formData[submitter.name] = submitter.value;
      }
    }
    applyFormDataTransforms({ children, formData });
    let body = { state: { ...state, ...formData } };
    submit(body, submitOptions);
  };

  let globalContext = {
    navigate,
    session_state: state,
    update_session_state(newState: Record<string, any>) {
      Object.assign(state, newState);
      submit({ state }, submitOptions);
    },
    set_session_state(newState: Record<string, any>) {
      for (let key in state) {
        state[key] = newState[key];
      }
      submit({ state }, submitOptions);
    },
    rerun: onSubmit,
  };
  if (typeof window !== "undefined") {
    // @ts-ignore
    window.gui = globalContext;
  }

  if (!children) return <></>;

  return (
    <div data-prismjs-copy="📋 Copy" data-prismjs-copy-success="✅ Copied!">
      <form
        ref={formRef}
        id={"gooey-form"}
        onChange={onChange}
        onSubmit={onSubmit}
        noValidate
      >
        <GlobalContextProvider value={globalContext}>
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </GlobalContextProvider>
      </form>
      <script
        async
        defer
        data-manual
        src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-core.min.js"
        integrity="sha512-9khQRAUBYEJDCDVP2yw3LRUQvjJ0Pjx0EShmaQjcHa6AXiOv6qHQu9lCAIR8O+/D8FtaCoJ2c0Tf9Xo7hYH01Q=="
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
      />
      <script
        async
        defer
        src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"
        integrity="sha512-SkmBfuA2hqjzEVpmnMt/LINrjop3GKWqsuLSSB3e7iBmYK7JuWw4ldmmxwD9mdm2IRTTi0OxSAfEGvgEi0i2Kw=="
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
      />
      <script
        async
        defer
        src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/toolbar/prism-toolbar.min.js"
        integrity="sha512-st608h+ZqzliahyzEpETxzU0f7z7a9acN6AFvYmHvpFhmcFuKT8a22TT5TpKpjDa3pt3Wv7Z3SdQBCBdDPhyWA=="
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
      />
      <script
        async
        defer
        src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/copy-to-clipboard/prism-copy-to-clipboard.min.js"
        integrity="sha512-/kVH1uXuObC0iYgxxCKY41JdWOkKOxorFVmip+YVifKsJ4Au/87EisD1wty7vxN2kAhnWh6Yc8o/dSAXj6Oz7A=="
        crossOrigin="anonymous"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}

export default withSentry(App);
