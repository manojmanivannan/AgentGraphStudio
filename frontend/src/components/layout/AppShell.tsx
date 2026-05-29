import { CanvasView } from "@/components/canvas/CanvasView";
import { SidebarRail } from "@/components/layout/SidebarRail";
import { TopBar } from "@/components/layout/TopBar";
import { PropertiesOverlay } from "@/components/PropertiesOverlay";
import { ChatOverlay } from "@/components/chat/ChatOverlay";

export function AppShell() {
  return (
    <div className="h-screen w-screen relative overflow-hidden bg-[var(--color-base)]">
      {/* Canvas fills the entire viewport */}
      <div className="absolute inset-0 z-0">
        <CanvasView />
      </div>

      {/* Top breadcrumb bar */}
      <TopBar />

      {/* Left sidebar rail */}
      <SidebarRail />

      {/* Overlay panels (slide in from right) */}
      <PropertiesOverlay />
      <ChatOverlay />
    </div>
  );
}