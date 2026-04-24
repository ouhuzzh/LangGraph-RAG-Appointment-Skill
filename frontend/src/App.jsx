import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ClearConfirmDialog from "./components/ClearConfirmDialog";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import { useChatSession } from "./hooks/useChatSession";
import { useDocuments } from "./hooks/useDocuments";
import { useSystemStatus } from "./hooks/useSystemStatus";

export default function App() {
  const [activeView, setActiveView] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const system = useSystemStatus();
  const chat = useChatSession({
    apiBaseUrl: system.apiBaseUrl,
    setApiBaseUrl: system.setApiBaseUrl,
    refreshStatus: system.refreshStatus,
    setIsConnected: system.setIsConnected,
  });
  const documents = useDocuments({
    apiBaseUrl: system.apiBaseUrl,
    setApiBaseUrl: system.setApiBaseUrl,
    refreshStatus: system.refreshStatus,
  });

  function navigate(view) {
    setActiveView(view);
    setSidebarOpen(false);
  }

  return (
    <div className="app">
      <Sidebar
        status={system.status}
        activeView={activeView}
        onNavigate={navigate}
        onClear={() => setClearDialogOpen(true)}
        onRefresh={system.refreshStatus}
        mobileOpen={sidebarOpen}
        onMobileClose={() => setSidebarOpen(false)}
      />

      {activeView === "documents" ? (
        <DocumentsPage
          documentsState={documents}
          onMenuClick={() => setSidebarOpen(true)}
        />
      ) : (
        <ChatPage
          chat={chat}
          isConnected={system.isConnected}
          onMenuClick={() => setSidebarOpen(true)}
        />
      )}

      <ClearConfirmDialog
        open={clearDialogOpen}
        onConfirm={async () => {
          setClearDialogOpen(false);
          await chat.clearChat();
        }}
        onCancel={() => setClearDialogOpen(false)}
      />
    </div>
  );
}
