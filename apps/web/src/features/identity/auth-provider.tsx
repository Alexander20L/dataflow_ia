"use client";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, ApiError, requireData, setCsrfToken } from "@/lib/api";

type AuthSession = components["schemas"]["SessionResponse"];
type AuthState = {
  session: AuthSession | null | undefined;
  loading: boolean;
  error: Error | null;
  retry: () => void;
  acceptSession: (session: AuthSession) => Promise<void>;
  logout: () => Promise<void>;
};
const AuthContext = createContext<AuthState | null>(null);
export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("AuthProvider requerido");
  return auth;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["session"],
    retry: false,
    staleTime: 60000,
    refetchOnWindowFocus: "always",
    queryFn: async ({ signal }) => {
      const result = await api.GET("/api/v1/auth/me", { signal });
      if (result.response.status === 401) {
        setCsrfToken(null);
        return null;
      }
      const session = requireData(result);
      setCsrfToken(session.csrf_token);
      return session;
    },
  });
  useEffect(() => {
    function expired() {
      void client.cancelQueries().then(() => {
        client.removeQueries({ predicate: (q) => q.queryKey[0] !== "session" });
        client.getMutationCache().clear();
        client.setQueryData(["session"], null);
      });
    }
    window.addEventListener("dataflow:session-expired", expired);
    return () =>
      window.removeEventListener("dataflow:session-expired", expired);
  }, [client]);
  useEffect(() => {
    if (!query.data) return;
    const delay = Math.max(
      0,
      new Date(query.data.expires_at).getTime() - Date.now(),
    );
    const timeout = setTimeout(
      () => {
        void client.invalidateQueries({ queryKey: ["session"] });
      },
      Math.min(delay + 100, 2147483647),
    );
    return () => clearTimeout(timeout);
  }, [client, query.data]);
  return (
    <AuthContext.Provider
      value={{
        session: query.data,
        loading: query.isPending,
        error: query.error,
        retry: () => {
          void query.refetch();
        },
        acceptSession: async (session) => {
          await client.cancelQueries();
          client.removeQueries({
            predicate: (q) => q.queryKey[0] !== "session",
          });
          client.getMutationCache().clear();
          setCsrfToken(session.csrf_token);
          client.setQueryData(["session"], session);
        },
        logout: async () => {
          const result = await api.POST("/api/v1/auth/logout");
          if (!result.response.ok && result.response.status !== 401)
            throw new ApiError(
              "No se pudo cerrar la sesión. Inténtalo otra vez.",
              result.response.status,
            );
          await client.cancelQueries();
          setCsrfToken(null);
          client.removeQueries({
            predicate: (q) => q.queryKey[0] !== "session",
          });
          client.getMutationCache().clear();
          client.setQueryData(["session"], null);
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
