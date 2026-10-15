"use client";

import { Show, SignInButton, UserButton } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";

export function AccountMenu() {
  return (
    <>
      <Show when="signed-in">
        <UserButton />
      </Show>
      <Show when="signed-out">
        <SignInButton mode="modal">
          <Button size="sm">Sign in</Button>
        </SignInButton>
      </Show>
    </>
  );
}
