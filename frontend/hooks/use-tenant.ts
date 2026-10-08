import { useQuery } from "@tanstack/react-query";

import { fetchTenant, tenantKeys } from "@/lib/api/tenant";

/**
 * The company currency (SPEC-FE-048), for responses that carry no currency of
 * their own (dashboard summary, sales summary, top products). Same query key
 * and staleTime as the sidebar's tenant query, so it adds no request.
 */
export function useCompanyCurrency(): string | null {
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant, staleTime: 60_000 });
  return tenant.data?.currency ?? null;
}
