import React, { lazy } from "react";
import { ClientOnly } from "remix-utils";
import LoadingFallback from "./loadingfallback";

export function lazyImport<T>(
  loader: () => Promise<T>,
  {
    fallback,
  }: { fallback?: (props: Record<string, any>) => React.ReactNode } = {}
): T {
  return new Proxy(
    {},
    {
      get: (_, prop) => {
        const Component = lazy(() => {
          return loader().then((mod: any) => {
            if (prop == "default") {
              return mod;
            } else {
              return { default: mod[prop] };
            }
          });
        });

        return (props: any) => {
          return (
            <ClientOnlySuspense fallback={fallback && fallback(props)}>
              {() => <Component {...props} />}
            </ClientOnlySuspense>
          );
        };
      },
    }
  ) as T;
}

export function ClientOnlySuspense({
  children,
  fallback,
}: {
  children: () => React.ReactNode;
  fallback?: React.ReactNode;
}) {
  return (
    <ClientOnly fallback={fallback ?? <LoadingFallback />}>
      {() => {
        return (
          <React.Suspense fallback={fallback ?? <LoadingFallback />}>
            {children()}
          </React.Suspense>
        );
      }}
    </ClientOnly>
  );
}
