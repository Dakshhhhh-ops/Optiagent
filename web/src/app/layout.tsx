import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { ClerkProvider } from "@clerk/nextjs";

import { AppSidebar } from "@/components/app-sidebar";
import { AuthBridge } from "@/components/auth-bridge";
import { Providers } from "@/components/providers";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { CLERK_ENABLED } from "@/lib/auth-config";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "OptiAgent", template: "%s · OptiAgent" },
  description: "Natural language to verified optimization models",
};

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <SidebarProvider>
        {/* Hidden when printing so reports print without the app chrome. */}
        <div className="contents print:hidden">
          <AppSidebar />
        </div>
        <SidebarInset>{children}</SidebarInset>
      </SidebarProvider>
    </Providers>
  );
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        {CLERK_ENABLED ? (
          <ClerkProvider>
            <AuthBridge />
            <Shell>{children}</Shell>
          </ClerkProvider>
        ) : (
          <Shell>{children}</Shell>
        )}
      </body>
    </html>
  );
}
