import { Compass, House, Search, Bookmark, Sparkles } from "lucide-react";

export const navItems = [
  { to: "/", label: "Home", icon: House, end: true, requiresAuth: false },
  { to: "/explore", label: "Explore", icon: Compass, end: false, requiresAuth: false },
  { to: "/search", label: "Search", icon: Search, end: false, requiresAuth: false },
  { to: "/recommendations", label: "For you", icon: Sparkles, end: false, requiresAuth: true },
  { to: "/watchlist", label: "Watchlist", icon: Bookmark, end: false, requiresAuth: true },
] as const;
