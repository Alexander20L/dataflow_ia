"use client";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="error-page">
      <h1>No pudimos abrir esta vista</h1>
      <p>
        Intenta cargarla de nuevo. Los datos de demostración guardados no se
        modificarán.
      </p>
      <Button onClick={reset}>Volver a intentar</Button>
    </main>
  );
}
