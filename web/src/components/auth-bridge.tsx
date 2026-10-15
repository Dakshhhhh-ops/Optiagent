"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";

import { setTokenGetter } from "@/lib/api";

/** Lets the API client attach the signed-in user's Clerk session token to every request. */
export function AuthBridge() {
  const { getToken } = useAuth();
  useEffect(() => {
    setTokenGetter(() => getToken());
    return () => setTokenGetter(null);
  }, [getToken]);
  return null;
}
