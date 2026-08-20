import { NextResponse, type NextRequest } from "next/server";

/**
 * Redirection de confort, pas de sécurité (plan.md § 3.4) : le cookie httpOnly
 * `cardan_session` n'est ici que vérifié présent, jamais décodé — la vérité
 * d'authentification/autorisation reste `GET /auth/me` et le cloisonnement backend.
 */
const SESSION_COOKIE = "cardan_session";
const PUBLIC_PATHS = ["/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  const isPublicPath = pathname === "/" || PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (!hasSession && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (hasSession && pathname === "/login") {
    return NextResponse.redirect(new URL("/vehicules", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Assets PWA exclus explicitement (manifest.json, sw.js, icônes, page hors-ligne) : un
  // 307 vers /login sur `sw.js` casse l'enregistrement du service worker (l'origine du
  // script doit répondre 200, sans redirection), et un manifeste servi en HTML invalide
  // le critère d'installabilité — ni l'un ni l'autre n'a de session à vérifier.
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|demo-photos|manifest\\.json|sw\\.js|hors-ligne\\.html|icons/).*)",
  ],
};
