import { NextResponse, type NextRequest } from "next/server";

/**
 * Route guard (Next.js 16 "proxy", formerly middleware): signed-out visitors to authenticated areas
 * are redirected to /login?next=... before any rendering. This only checks for the presence of the
 * Django session cookie; the API validates the session and authorises every request.
 */
export const PROTECTED_PREFIXES = ["/candidate", "/hr", "/admin", "/account"] as const;
export const SESSION_COOKIE = "sessionid";

export function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function loginRedirect(request: NextRequest): NextResponse | null {
  const { pathname, search } = request.nextUrl;
  if (!isProtected(pathname) || request.cookies.has(SESSION_COOKIE)) return null;
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export function proxy(request: NextRequest) {
  return loginRedirect(request) ?? NextResponse.next();
}

export const config = {
  matcher: ["/candidate/:path*", "/hr/:path*", "/admin/:path*", "/account/:path*"],
};
