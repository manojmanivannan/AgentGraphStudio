import { CanvasToolbar } from "@/components/toolbar/CanvasToolbar";
import { CanvasView } from "@/components/canvas/CanvasView";
import { PropertiesSidebar } from "@/components/PropertiesSidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";

export function AppShell() {
  return (
    <div className="h-screen w-screen flex flex-col bg-gray-50">
      <CanvasToolbar />
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1">
          <CanvasView />
        </div>
        <PropertiesSidebar />
        <ChatPanel />
      </div>
    </div>
  );
}
