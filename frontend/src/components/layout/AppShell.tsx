import { CanvasToolbar } from "@/components/toolbar/CanvasToolbar";
import { CanvasView } from "@/components/canvas/CanvasView";
import { Sidebar } from "@/components/sidebar/Sidebar";

export function AppShell() {
  return (
    <div className="h-screen w-screen flex flex-col bg-gray-50">
      <CanvasToolbar />
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1">
          <CanvasView />
        </div>
        <Sidebar />
      </div>
    </div>
  );
}
