import Link from "next/link";
import type { ReactNode } from "react";

export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <Link href="/" className="font-semibold tracking-tight">
            Cardan
          </Link>
          <Link
            href="/login"
            className="rounded-md px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted"
          >
            Se connecter
          </Link>
        </div>
      </header>
      <main id="contenu-principal" className="flex flex-1 flex-col">
        {children}
      </main>
    </div>
  );
}
