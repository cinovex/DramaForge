import { NextRequest, NextResponse } from "next/server";

const servicePaths = [
  "/api",
  "/studio-api",
  "/studio-mcp",
  "/studio-a2a",
  "/health",
  "/storage",
  "/videos-browse",
  "/canvasApp",
  "/_next",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (servicePaths.some(path => pathname === path || pathname.startsWith(`${path}/`)) || pathname === "/favicon.ico") {
    return NextResponse.next();
  }
  if (pathname !== "/") return NextResponse.redirect(new URL("/#/home", request.url));
  return NextResponse.rewrite(new URL("/canvasApp/index.html", request.url));
}

export const config = { matcher: ["/:path*"] };
