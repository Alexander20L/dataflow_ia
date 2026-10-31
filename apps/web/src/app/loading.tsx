export default function Loading() {
  return (
    <main
      className="loading-screen"
      aria-busy="true"
      aria-label="Cargando workspace"
    >
      <div className="skeleton" />
      <div className="skeleton" />
      <div className="skeleton" />
    </main>
  );
}
