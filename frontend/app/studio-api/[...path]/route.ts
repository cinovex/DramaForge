import { proxyStudioRequest } from "@/lib/studioProxy";

type RouteContext = { params: { path: string[] } };
const proxy = (request: Request, context: RouteContext) => proxyStudioRequest(request, "api", context.params.path);

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
