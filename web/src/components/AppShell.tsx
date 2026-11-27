import {
  Braces, ChartColumn, ChevronsUpDown, CircleCheckBig, FolderOpen, GitBranch, KeyRound, LogOut, Play, ScrollText, Settings,
  TriangleAlert,
} from "lucide-react";
import type { ComponentType } from "react";
import { api, csrfHeader, type Schema } from "@/api/client";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu,
  SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar,
} from "@/components/ui/sidebar";
import { Link } from "./Link";

type Icon = ComponentType<{ className?: string }>;
type Item = { to: string; label: string; icon: Icon; current: boolean; badge?: number };

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
}

function NavGroup({ label, items, go }: { label?: string; items: Item[]; go: (to: string) => void }) {
  const { setOpenMobile } = useSidebar();
  return (
    <SidebarGroup>
      {label && <SidebarGroupLabel>{label}</SidebarGroupLabel>}
      <SidebarMenu>
        {items.map((it) => (
          <SidebarMenuItem key={it.to}>
            <SidebarMenuButton asChild isActive={it.current} tooltip={it.label}>
              <Link to={it.to} go={go} current={it.current} onNavigate={() => setOpenMobile(false)}>
                <it.icon />
                <span>{it.label}</span>
              </Link>
            </SidebarMenuButton>
            {it.badge ? <SidebarMenuBadge>{it.badge}</SidebarMenuBadge> : null}
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
}

export function AppShell({
  me, project, first, here, mine, allMine, go, children,
}: {
  me: Schema["Me"];
  project?: Schema["ProjectOut"];
  first?: string;
  here: string;
  mine: number;
  allMine: number;
  go: (to: string) => void;
  children: React.ReactNode;
}) {
  const projectItems: Item[] = project
    ? [
        { to: `/p/${project.id}/runs`, label: "Runs", icon: Play, current: here === "runs" },
        { to: `/p/${project.id}/decisions`, label: "Decision Room", icon: CircleCheckBig, current: here === "decisions", badge: mine },
        { to: `/p/${project.id}/errors`, label: "Errors", icon: TriangleAlert, current: here === "errors", badge: project.problem_runs },
        { to: `/p/${project.id}/pipeline`, label: "Pipeline", icon: GitBranch, current: here === "pipeline" },
        { to: `/p/${project.id}/variables`, label: "Variables", icon: Braces, current: here === "variables" },
        { to: `/p/${project.id}/audit`, label: "Audit trail", icon: ScrollText, current: here === "audit" },
        ...(project.roles.includes("owner") || me.roles.includes("admin")
          ? [{ to: `/p/${project.id}/access`, label: "Access", icon: KeyRound, current: here === "access" }]
          : []),
      ]
    : [];
  const orgItems: Item[] = [
    { to: "/overview", label: "Overview", icon: ChartColumn, current: first === "overview" },
    { to: "/", label: "All projects", icon: FolderOpen, current: !project && first !== "decisions" && first !== "admin" && first !== "overview" },
    { to: "/decisions", label: "Decision Room", icon: CircleCheckBig, current: first === "decisions", badge: allMine },
    ...(me.roles.includes("admin") ? [{ to: "/admin", label: "Administration", icon: Settings, current: first === "admin" }] : []),
  ];

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="flex items-baseline gap-2 px-2 pt-1 group-data-[collapsible=icon]:hidden">
            <span className="text-lg font-semibold tracking-tight">ASAC</span>
            <span className="text-xs text-muted-foreground">governance</span>
          </div>
          <div className="rounded-lg border bg-background px-3 py-2 group-data-[collapsible=icon]:hidden">
            <div className="truncate text-sm font-medium">{project?.name ?? "All projects"}</div>
            <div className="truncate text-xs text-muted-foreground">{me.organization}</div>
          </div>
        </SidebarHeader>

        <SidebarContent>
          {project && <NavGroup items={projectItems} go={go} />}
          <NavGroup label="Organisation" items={orgItems} go={go} />
        </SidebarContent>

        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent">
                    <Avatar className="size-8 rounded-lg">
                      <AvatarFallback className="rounded-lg text-xs">{initials(me.name)}</AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-left leading-tight">
                      <span className="truncate text-sm font-medium">{me.name}</span>
                      <span className="truncate text-xs text-muted-foreground">
                        {project ? `${project.roles.join(", ") || "reader"} · ${project.id}` : me.roles.join(", ")}
                      </span>
                    </div>
                    <ChevronsUpDown className="ml-auto size-4" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="top" align="start" className="w-56">
                  <DropdownMenuItem
                    onSelect={() => {
                      void api.POST("/logout", { headers: csrfHeader() }).then(() => window.location.assign("/app/"));
                    }}
                  >
                    <LogOut /> Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>

      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
