import { useEffect, useState } from "react";

/**
 * Mientras `dirty` sea verdadero, avisa al recargar/cerrar e intercepta la navegación por
 * enlaces internos. Devuelve la ruta pendiente para que el componente pida confirmación.
 */
export function useUnsavedGuard(dirty: boolean) {
  const [route, setRoute] = useState<string | null>(null);
  useEffect(() => {
    if (!dirty) return;
    const unload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const click = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor =
        event.target instanceof Element ? event.target.closest("a") : null;
      if (
        !(anchor instanceof HTMLAnchorElement) ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download")
      )
        return;
      const url = new URL(anchor.href, window.location.href);
      if (
        url.origin !== window.location.origin ||
        url.pathname.startsWith("/api/") ||
        url.pathname + url.search ===
          window.location.pathname + window.location.search
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      setRoute(url.pathname + url.search + url.hash);
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", click, true);
    };
  }, [dirty]);
  return [route, setRoute] as const;
}
