"use client";

import {
  Activity,
  FlaskConical,
  FolderKanban,
  LayoutDashboard,
  type LucideIcon,
  Sigma,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  /** Phase in which the page ships; rendered disabled until then. */
  comingIn?: number;
}

const NAV: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { title: "Overview", href: "/", icon: LayoutDashboard },
      { title: "New problem", href: "/problems/new", icon: Sparkles },
      { title: "Projects", href: "/projects", icon: FolderKanban },
    ],
  },
  {
    label: "Research",
    items: [{ title: "Benchmarks", href: "/benchmarks", icon: FlaskConical }],
  },
  {
    label: "System",
    items: [{ title: "Status", href: "/system", icon: Activity }],
  },
];

/** The navigation groups; `pathname` is null while the current URL is not known yet. */
function NavGroups({ pathname }: { pathname: string | null }) {
  return (
    <>
    {NAV.map((group) => (
      <SidebarGroup key={group.label}>
        <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {group.items.map((item) => (
              <SidebarMenuItem key={item.href}>
                {item.comingIn ? (
                  <>
                    <SidebarMenuButton disabled tooltip={item.title}>
                      <item.icon />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                    <SidebarMenuBadge className="text-muted-foreground">
                      P{item.comingIn}
                    </SidebarMenuBadge>
                  </>
                ) : (
                  <SidebarMenuButton
                    asChild
                    isActive={
                        pathname !== null &&
                        (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href))
                      }
                    tooltip={item.title}
                  >
                    <Link href={item.href}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    ))}
    </>
  );
}

/** Reads the URL. Kept in its own Suspense boundary so pages with dynamic routes can prerender. */
function LiveNavGroups() {
  return <NavGroups pathname={usePathname()} />;
}

export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <Sigma className="size-4" />
                </div>
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate font-semibold">OptiAgent</span>
                  <span className="truncate text-xs text-muted-foreground">
                    Verified optimization
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <Suspense fallback={<NavGroups pathname={null} />}>
          <LiveNavGroups />
        </Suspense>
      </SidebarContent>

      <SidebarFooter>
        <p className="px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          v0.1.0 · Phase 7
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
