import type { IconName } from "./icons";

// Navigation shared by the sidebar, the mobile tab bar / More sheet, the
// command palette and the top bar title. Sections and order follow the
// PilotSonic dashboard design (Main / Engines / Configuration); Marketing keeps
// its sub-pages (SPEC-FE-049, SPEC-FE-054) and Settings (SPEC-FE-036) stays.
// superAdmin (SPEC-FE-080): only PilotSonic's Super admin sees the child.
export type NavChild = { label: string; href: string; superAdmin?: boolean };
// minRole (SPEC-FE-078): the lowest app role that sees the item. Hiding is only a
// convenience; the backend enforces every permission.
export type NavItem = { label: string; href: string; icon: IconName; children?: NavChild[]; minRole?: Role };
export type Role = "viewer" | "agent" | "manager" | "admin" | "owner";
const ROLE_RANK: Record<string, number> = { viewer: 20, agent: 40, manager: 60, admin: 80, owner: 100 };
export type NavSection = { title: string; items: NavItem[] };

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Main",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: "grid" },
      { label: "Command Chat", href: "/chat", icon: "chat" },
    ],
  },
  {
    title: "Engines",
    items: [
      { label: "E-Commerce", href: "/ecommerce", icon: "bag" },
      { label: "Orders", href: "/orders", icon: "receipt" },
      { label: "Customers", href: "/customers", icon: "user" },
      {
        label: "Marketing",
        href: "/marketing",
        icon: "mega",
        children: [
          { label: "Paid Marketing", href: "/marketing/paid" },
          { label: "Organic Marketing", href: "/marketing/organic" },
          { label: "SocialAPI", href: "/marketing/organic/socialapi" },
          // Platform API keys and developer apps (SPEC-FE-080): the Super admin's section on /admin.
          { label: "Social API Configuration", href: "/admin#platforms", superAdmin: true },
        ],
      },
      { label: "Customer Service", href: "/customer", icon: "users" },
    ],
  },
  {
    title: "Configuration",
    items: [
      { label: "Social Accounts", href: "/marketing/organic/accounts", icon: "share" },
      { label: "Integrations", href: "/integrations", icon: "plug", minRole: "manager" },
      { label: "Branding", href: "/branding", icon: "palette" },
      { label: "Knowledge Base", href: "/kb", icon: "book" },
      { label: "Workflows", href: "/workflows", icon: "flow", minRole: "manager" },
      { label: "Analytics", href: "/analytics", icon: "chart" },
      { label: "Settings", href: "/settings", icon: "gear", minRole: "manager" },
    ],
  },
];

// SPEC-FE-068: only PilotSonic's Super admin sees this section (GET /platform/me).
export const SUPER_ADMIN_SECTION: NavSection = {
  title: "PilotSonic",
  items: [{ label: "Super admin", href: "/admin", icon: "star" }],
};

// The mobile tab bar's four fixed tabs (the design's Home / Agent / Store /
// Market); everything else is in the More sheet.
export const TAB_ITEMS: { label: string; href: string; icon: IconName }[] = [
  { label: "Home", href: "/dashboard", icon: "grid" },
  { label: "Agent", href: "/chat", icon: "chat" },
  { label: "Store", href: "/ecommerce", icon: "bag" },
  { label: "Market", href: "/marketing", icon: "mega" },
];

// Prompts the design offers as quick actions and palette commands. They open a
// new Command Chat with the text in the composer, ready to send.
export const AGENT_PROMPTS = [
  "Create 7 organic posts and schedule them",
  "Check my shipping setup",
  "How are my ads doing?",
  "What is low on stock?",
  "Any customers waiting for a reply?",
];

export function askHref(text: string): string {
  return `/chat?new=1&ask=${encodeURIComponent(text)}`;
}

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The sections this user sees: Super admin also gets the PilotSonic section and the superAdmin children. */
export function navSections(superAdmin: boolean | undefined): NavSection[] {
  if (superAdmin) return [...NAV_SECTIONS, SUPER_ADMIN_SECTION];
  return NAV_SECTIONS.map((s) => ({
    ...s,
    items: s.items.map((i) => (i.children ? { ...i, children: i.children.filter((c) => !c.superAdmin) } : i)),
  }));
}

/** Every page as [label, href], children included, for the palette and titles. */
/** The sections a role sees (unknown role = everything, until the profile loads). */
export function forRole(sections: NavSection[], role: string | null | undefined): NavSection[] {
  if (!role) return sections;
  const rank = ROLE_RANK[role] ?? 0;
  return sections.map((s) => ({ ...s, items: s.items.filter((i) => !i.minRole || rank >= ROLE_RANK[i.minRole]) }));
}

export function flatPages(sections: NavSection[]): NavChild[] {
  return sections.flatMap((s) => s.items.flatMap((i) => [{ label: i.label, href: i.href }, ...(i.children ?? [])]));
}

/** The top bar title: the label of the longest nav route matching the path. */
export function pageTitle(pathname: string, sections: NavSection[]): string {
  let best: NavChild | null = null;
  for (const p of flatPages(sections)) {
    if (isActive(pathname, p.href) && (!best || p.href.length > best.href.length)) best = p;
  }
  return best?.label ?? "PilotSonic";
}
