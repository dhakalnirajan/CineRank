import { Link } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { Logo } from "../navigation/Logo";

function FooterLink({ to, children }: { to: string; children: string }) {
  return (
    <Link
      to={to}
      className="block w-fit text-sm text-white/55 transition-colors hover:text-white"
    >
      {children}
    </Link>
  );
}

export function Footer() {
  const { status } = useAuth();

  return (
    <footer className="mt-20 border-t border-white/10 bg-[#0c0c0c]">
      <div className="page-shell py-12 sm:py-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.3fr_0.7fr_0.7fr_1fr] lg:gap-12">
          <div className="max-w-sm sm:col-span-2 lg:col-span-1">
            <Logo compact />
            <p className="mt-4 text-sm leading-relaxed text-white/55">
              A simpler way to find your next favorite.
            </p>
          </div>

          <nav aria-label="Explore" className="space-y-3.5">
            <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-white/35">
              Explore
            </h2>
            <FooterLink to="/explore">Browse catalogue</FooterLink>
            <FooterLink to="/genres">Genre guide</FooterLink>
          </nav>

          <nav aria-label="Community" className="space-y-3.5">
            <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-white/35">
              Community
            </h2>
            {status === "authenticated" ? (
              <>
                <FooterLink to="/watchlist">Your watchlist</FooterLink>
                <FooterLink to="/history">Rating history</FooterLink>
              </>
            ) : status === "anonymous" ? (
              <>
                <FooterLink to="/login">Sign in</FooterLink>
                <FooterLink to="/register">Create an account</FooterLink>
              </>
            ) : null}
          </nav>

          <div className="space-y-3.5">
            <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-white/35">
              Legal and attribution
            </h2>
            <p className="max-w-xs text-sm leading-relaxed text-white/55">
              Artwork & metadata belong to their original sources.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-white/10">
        <div className="page-shell py-5">
          <p className="text-xs text-white/40">© 2026 CineRank. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
