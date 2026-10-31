type Snapshot = { cleaned: boolean; dark: boolean };
const key = "dataflow-ui-v2";
export const initialSnapshot: Snapshot = {
  cleaned: false,
  dark: false,
};
let cached: Snapshot | undefined;
const listeners = new Set<() => void>();

export function getDemoSnapshot(): Snapshot {
  if (cached) return cached;
  cached = initialSnapshot;
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) || "null");
    if (value && typeof value === "object") {
      cached = {
        cleaned: "cleaned" in value && value.cleaned === true,
        dark: "dark" in value && value.dark === true,
      };
    }
  } catch {
    /* Persistencia opcional para la demo. */
  }
  return cached;
}
export function updateDemo(update: (current: Snapshot) => Snapshot) {
  cached = update(getDemoSnapshot());
  try {
    localStorage.setItem(key, JSON.stringify(cached));
  } catch {
    /* Continuar en memoria. */
  }
  listeners.forEach((listener) => listener());
}
export function subscribeDemo(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === key || event.key === null) {
      cached = undefined;
      listeners.forEach((notify) => notify());
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}
