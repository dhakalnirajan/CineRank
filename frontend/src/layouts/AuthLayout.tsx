import { Outlet } from "react-router-dom";
import { Header } from "../components/navigation/Header";

export function AuthLayout() {
  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-hidden bg-black">
      <div className="cinema-band absolute inset-0 -z-20" aria-hidden="true" />
      <div className="absolute inset-0 -z-10 bg-black/55" aria-hidden="true" />
      <div
        className="absolute inset-0 -z-10 opacity-70"
        style={{
          backgroundImage:
            "radial-gradient(42% 58% at 18% 40%, rgb(70 21 24 / 0.9) 0%, transparent 100%), radial-gradient(36% 52% at 82% 30%, rgb(25 34 71 / 0.9) 0%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      <Header />
      <main className="relative z-10 flex flex-1 items-center justify-center px-4 pb-10 pt-[calc(var(--header-height)+2.5rem)] sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
