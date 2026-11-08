import type { Metadata } from "next";
import { Providers } from "@/lib/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataFlow AI — Tu próximo hallazgo empieza aquí",
  description:
    "Análisis automático de tus archivos: sube un CSV o Excel y obtén tu dashboard.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
