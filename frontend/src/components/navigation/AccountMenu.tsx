import {
  Bookmark,
  History,
  LogOut,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { mediaUrl } from "../../utils/mediaUrl";

interface AccountMenuProps {
  username: string;
  email: string | null;
  avatarUrl?: string | null;
  onSignOut: () => void;
}

export function AccountMenu({ username, email, avatarUrl, onSignOut }: AccountMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const { pathname } = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Account menu for ${username}`}
        aria-expanded={open}
        aria-controls="account-menu"
        onClick={() => setOpen((current) => !current)}
        className="grid size-[2.25rem] shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#f6121d] to-[#5c070b] text-white ring-1 ring-white/20 transition-[box-shadow,transform] duration-[var(--motion-fast)] hover:ring-accent/80 active:scale-95"
      >
        {avatarUrl ? (
          <img src={mediaUrl(avatarUrl)} alt="" className="size-full object-cover" />
        ) : (
          <UserRound className="size-5" aria-hidden="true" />
        )}
      </button>

      {open ? (
        <div className="animate-fade-up absolute right-0 top-full z-50 w-60 origin-top-right pt-2">
          <div
            id="account-menu"
            className="overflow-hidden rounded-xl border border-white/10 bg-[#0c0c0c] shadow-2xl shadow-black/70"
          >
            <div className="border-b border-white/10 px-4 py-3.5">
              <p className="truncate text-sm font-semibold text-white">{username}</p>
              {email ? (
                <p className="mt-0.5 truncate text-xs text-white/45">{email}</p>
              ) : null}
            </div>

            <div className="p-1.5">
              <AccountLink to="/profile" icon={UserRound} label="Profile" />
              <AccountLink to="/watchlist" icon={Bookmark} label="Watchlist" />
              <AccountLink to="/history" icon={History} label="Rating history" />
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onSignOut();
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-white/65 transition-colors duration-[var(--motion-fast)] hover:bg-white/[0.06] hover:text-white"
              >
                <LogOut className="size-4 shrink-0" aria-hidden="true" />
                Sign out
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function AccountLink({
  to,
  icon: Icon,
  label,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-white/65 transition-colors duration-[var(--motion-fast)] hover:bg-white/[0.06] hover:text-white"
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {label}
    </Link>
  );
}
