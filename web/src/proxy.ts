import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import { CLERK_ENABLED } from "@/lib/auth-config";

// Pages that hold a user's own work. Everything else (overview, benchmarks, status) is public.
const isPrivate = createRouteMatcher(["/problems(.*)", "/projects(.*)"]);

export default CLERK_ENABLED
  ? clerkMiddleware(async (auth, request) => {
      if (isPrivate(request)) await auth.protect();
    })
  : () => NextResponse.next();

export const config = {
  matcher: [
    // Skip Next.js internals and static files.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
