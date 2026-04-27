"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  History,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "SLO board", icon: LayoutDashboard },
  { href: "/incidents", label: "Incidents", icon: Activity },
  { href: "/recommendations", label: "Recommendations", icon: Inbox },
  { href: "/actions", label: "Action history", icon: History },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-60 flex-col border-r border-[color:var(--color-border)] bg-[color:var(--color-bg)] px-3 py-4"
    >
      <div className="px-3 pb-6">
        <span className="text-base font-semibold tracking-tight">RepoPulse</span>
        <span
          className="ml-2 text-xs uppercase text-[color:var(--color-fg-dim)]"
          aria-label="Operator console"
        >
          Operator
        </span>
      </div>
      <ul className="flex flex-col gap-1">
        {NAV.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-11 items-center gap-3 rounded-[var(--radius-sm)] px-3",
                  "text-sm transition-colors",
                  active
                    ? "border-l-2 border-[color:var(--color-primary)] bg-[color:var(--color-primary-soft)] pl-[10px] text-[color:var(--color-fg)]"
                    : "text-[color:var(--color-fg-muted)] hover:bg-[color:var(--color-bg-elev)] hover:text-[color:var(--color-fg)]",
                )}
              >
                <Icon
                  size={16}
                  aria-hidden
                  className={
                    active
                      ? "text-[color:var(--color-primary)]"
                      : "text-[color:var(--color-fg-dim)]"
                  }
                />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
