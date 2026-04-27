import { NextResponse, type NextRequest } from "next/server";

const PUBLIC = ["/login", "/api", "/_next", "/favicon.ico"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }
  const tok = req.cookies.get("jf_session")?.value;
  if (!tok) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  // Redirect root to /home for authenticated users.
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/home", req.url));
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
