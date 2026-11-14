"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CheckCircle2, X } from "lucide-react";
import type { Project } from "./project";
import { AuthProvider, useAuth } from "@/features/identity/auth-provider";
import { AuthGate } from "@/features/identity/auth-gate";
import { projectView, useProjects } from "@/features/projects/api";
import {
  getUiSnapshot,
  initialSnapshot,
  subscribeUi,
  updateUi,
} from "./ui-store";

type AppState = {
  projects: Project[];
  projectTotal: number;
  notify: (message: string) => void;
  dark: boolean;
  toggleTheme: () => void;
  ready: boolean;
};
const AppContext = createContext<AppState | null>(null);
export function useApp() {
  const app = useContext(AppContext);
  if (!app) throw new Error("AppProvider requerido");
  return app;
}
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WorkspaceProvider>
          <AuthGate>{children}</AuthGate>
        </WorkspaceProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const remote = useProjects("", undefined, 100, 0, !!session);
  const projects = remote.data?.items.map(projectView) ?? [];
  const { dark } = useSyncExternalStore(
    subscribeUi,
    getUiSnapshot,
    () => initialSnapshot,
  );
  const ready = useSyncExternalStore(
    subscribeUi,
    () => true,
    () => false,
  );
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!ready) return;
    document.documentElement.classList.toggle("dark", dark);
  }, [dark, ready]);
  useEffect(() => {
    if (message) {
      const timer = setTimeout(() => setMessage(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [message]);
  return (
    <AppContext.Provider
      value={{
        projects,
        projectTotal: remote.data?.total ?? 0,
        notify: setMessage,
        dark,
        toggleTheme: () => updateUi((s) => ({ ...s, dark: !s.dark })),
        ready,
      }}
    >
      {children}
      {message && (
        <div className="toast" role="status">
          <CheckCircle2 size={19} />
          <span>{message}</span>
          <button
            aria-label="Cerrar notificación"
            onClick={() => setMessage("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </AppContext.Provider>
  );
}
