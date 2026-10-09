"use client";

import {
  isServer,
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { rememberNewThingTab } from "@/hooks/use-new-tab";
import { clearAuthToken, getAuthToken } from "@/lib/auth/token";
import { ApiError } from "@/lib/types/common";

// 401 boundary (SPEC-FE-004 edge case). apiFetch itself is unchanged (SPEC-FE-003):
// it only throws the ApiError. Here, at the query layer that every (app) page's
// data goes through, a 401 from any query or mutation means the stored token was
// rejected (expired after 15 minutes, or its user was disabled/deleted), so the
// token is cleared and the browser does a full navigation to /login, which also
// discards every cached tenant response. It fires only after the query's retry
// (retry: 1) is exhausted.
function handleUnauthorized(error: unknown): void {
  if (!isServer && error instanceof ApiError && error.status === 401) {
    clearAuthToken();
    window.location.replace("/login");
  }
}

// TanStack Query provider for the app shell (SPEC-FE-003). The defaults below
// (staleTime 30s, one retry) are a starting point; any later spec may override
// them per query.
function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleUnauthorized }),
    mutationCache: new MutationCache({ onError: handleUnauthorized }),
    defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
  });
}

let browserQueryClient: QueryClient | undefined;

// Per TanStack Query's Next.js App Router guidance: a fresh client per server
// render (never shared between requests), and one singleton in the browser so
// React strict-mode double renders and suspending re-renders reuse it instead
// of creating a new cache.
function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient();
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}

export default function Providers({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();
  const router = useRouter();
  // Route guard (SPEC-FE-004 rule 6). It lives here rather than in
  // app/(app)/layout.tsx because that layout is a server component and can't
  // read localStorage; this client component wraps every (app) route, so the
  // check still runs before any sidebar/topbar/page content renders. Nothing is
  // rendered until the check passes (including on the server), so the shell
  // never flashes for a logged-out visitor. Client-side only: a middleware /
  // server check is out of scope.
  const [authenticated, setAuthenticated] = useState(false);
  useEffect(() => {
    rememberNewThingTab(); // SPEC-FE-058: a tab opened for a new thing (nt=1)
    if (getAuthToken() === null) {
      router.replace("/login");
    } else {
      setAuthenticated(true);
    }
  }, [router]);

  if (!authenticated) {
    return null;
  }
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
