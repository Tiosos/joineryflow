import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/session-cookie";

const PUBLIC = ["/login", "/api", "/_next", "/favicon.ico"];

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }
  const tok = req.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (!tok) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  // Redirect root to /dashboard for authenticated users.
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }
  // Pass the pathname as a request header so Server Components can read it.
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-pathname", pathname);
  return NextResponse.next({
    request: { headers: requestHeaders },
  });
}

export const config = {
  matcher: "/((?!_next/static|_next/image|favicon.ico).*)",
};
