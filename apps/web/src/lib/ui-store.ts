type Snapshot = { dark: boolean };
const key = "dataflow-ui-v2";
export const initialSnapshot: Snapshot = {
  dark: false,
};
let cached: Snapshot | undefined;
const listeners = new Set<() => void>();

export function getUiSnapshot(): Snapshot {
  if (cached) return cached;
  cached = initialSnapshot;
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) || "null");
    if (value && typeof value === "object") {
      cached = {
        dark: "dark" in value && value.dark === true,
      };
    }
  } catch {
    /* Preferencia opcional: sin almacenamiento se usa el tema claro. */
  }
  return cached;
}
export function updateUi(update: (current: Snapshot) => Snapshot) {
  cached = update(getUiSnapshot());
  try {
    localStorage.setItem(key, JSON.stringify(cached));
  } catch {
    /* Continuar en memoria. */
  }
  listeners.forEach((listener) => listener());
}
export function subscribeUi(listener: () => void) {
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
