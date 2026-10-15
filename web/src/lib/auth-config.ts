/**
 * Clerk sign-in is on when a publishable key is configured (production), or when
 * NEXT_PUBLIC_AUTH=clerk forces it (e.g. to try Clerk's keyless development mode).
 * Without either, the app runs in local single-user mode.
 */
export const CLERK_ENABLED =
  Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) || process.env.NEXT_PUBLIC_AUTH === "clerk";
