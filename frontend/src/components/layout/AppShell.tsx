import { Outlet, useLocation } from "react-router-dom";
import { cn } from "../../utils/cn";
import { Footer } from "./Footer";
import { Header } from "../navigation/Header";
import { MobileNav } from "../navigation/MobileNav";

export function AppShell() {
  const { pathname } = useLocation();
  const isHome = pathname === "/";

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-control focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-black"
      >
        Skip to content
      </a>
      <Header />
      <main
        id="main"
        className={cn("flex-1", !isHome && "pt-[var(--header-height)]")}
      >
        <Outlet />
      </main>
      <Footer />
      <div className="h-16 lg:hidden" aria-hidden="true" />
      <MobileNav />
    </div>
  );
}
