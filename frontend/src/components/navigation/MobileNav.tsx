import { LogIn } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { cn } from "../../utils/cn";
import { navItems } from "./navItems";

export function MobileNav() {
  const { status } = useAuth();

  const items = [
    ...navItems.filter((item) => !item.requiresAuth || status === "authenticated"),
    ...(status === "anonymous"
      ? [{ to: "/login", label: "Sign in", icon: LogIn, end: false, requiresAuth: false }]
      : []),
  ];

  return (
    <nav
      aria-label="Primary mobile"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-black/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
    >
      <ul
        className="grid h-16"
        style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
      >
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.label}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-full flex-col items-center justify-center gap-1 text-[0.6875rem] font-medium transition-colors",
                    isActive ? "text-white" : "text-white/55 hover:text-white/80",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive ? (
                      <span
                        aria-hidden="true"
                        className="absolute inset-x-6 top-0 h-0.5 bg-accent"
                      />
                    ) : null}
                    <Icon
                      className={cn("size-5", isActive ? "text-accent" : "text-current")}
                      aria-hidden="true"
                    />
                    {item.label}
                  </>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
