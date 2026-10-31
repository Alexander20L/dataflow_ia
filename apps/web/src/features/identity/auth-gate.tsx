"use client";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowRight, LockKeyhole, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, errorMessage, requireData } from "@/lib/api";
import { useAuth } from "./auth-provider";

export function AuthGate({ children }: { children: ReactNode }) {
  const { session, loading, error, retry } = useAuth();
  if (loading)
    return (
      <main className="loading-screen" aria-label="Verificando sesión">
        <div className="skeleton" />
        <div className="skeleton" />
      </main>
    );
  if (error)
    return (
      <main className="auth-page">
        <section className="panel auth-card">
          <h1>No pudimos conectar</h1>
          <p>{errorMessage(error)}</p>
          <Button onClick={retry}>Volver a intentar</Button>
        </section>
      </main>
    );
  if (session) return children;
  return <AuthScreen />;
}

function AuthScreen() {
  const [register, setRegister] = useState(false);
  return (
    <main className="auth-page">
      <div className="auth-intro">
        <span className="brand-icon">
          <Workflow size={28} />
        </span>
        <span className="eyebrow">DATAFLOW AI</span>
        <h1>
          Tus datos.
          <br />
          Tu próximo hallazgo.
        </h1>
        <p>
          Un espacio de análisis con control, claridad y evidencia en cada paso.
        </p>
        <div className="info-banner">
          <LockKeyhole size={19} />
          <span>
            Tus proyectos y CSV se guardan en tu cuenta. El perfil y la calidad
            se calculan con evidencia; la IA sigue en fase de demostración.
          </span>
        </div>
      </div>
      <section className="panel auth-card">
        <h2>{register ? "Crea tu cuenta" : "Bienvenido de nuevo"}</h2>
        <p>
          {register
            ? "Comienza con tu espacio personal de trabajo."
            : "Inicia sesión para acceder a tus proyectos."}
        </p>
        <AuthForm key={String(register)} registerMode={register} />
        <p className="auth-toggle">
          {register ? "¿Ya tienes cuenta?" : "¿Es tu primera vez?"}{" "}
          <button className="text-link" onClick={() => setRegister(!register)}>
            {register ? "Inicia sesión" : "Crear cuenta"}
          </button>
        </p>
      </section>
    </main>
  );
}

function AuthForm({ registerMode }: { registerMode: boolean }) {
  const { acceptSession } = useAuth();
  const [error, setError] = useState("");
  const schema = z
    .object({
      name: z.string().trim().max(80),
      email: z.email("Escribe un correo válido."),
      password: z
        .string()
        .min(
          registerMode ? 12 : 1,
          registerMode
            ? "Utiliza al menos 12 caracteres."
            : "Escribe tu contraseña.",
        )
        .max(128),
    })
    .refine((v) => !registerMode || v.name.length >= 2, {
      path: ["name"],
      message: "Escribe al menos 2 caracteres.",
    });
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", password: "" },
  });
  async function submit(values: z.infer<typeof schema>) {
    setError("");
    try {
      const result = registerMode
        ? await api.POST("/api/v1/auth/register", { body: values })
        : await api.POST("/api/v1/auth/login", {
            body: { email: values.email, password: values.password },
          });
      await acceptSession(requireData(result));
    } catch (error) {
      setError(errorMessage(error));
    }
  }
  return (
    <form className="auth-form" onSubmit={handleSubmit(submit)}>
      {registerMode && (
        <>
          <label htmlFor="auth-name">Nombre</label>
          <input
            id="auth-name"
            autoComplete="name"
            {...register("name")}
            aria-invalid={!!errors.name}
          />
          {errors.name && <p className="field-error">{errors.name.message}</p>}
        </>
      )}
      <label htmlFor="auth-email">Correo electrónico</label>
      <input
        id="auth-email"
        type="email"
        autoComplete="email"
        {...register("email")}
        aria-invalid={!!errors.email}
      />
      {errors.email && <p className="field-error">{errors.email.message}</p>}
      <label htmlFor="auth-password">Contraseña</label>
      <input
        id="auth-password"
        type="password"
        autoComplete={registerMode ? "new-password" : "current-password"}
        {...register("password")}
        aria-invalid={!!errors.password}
      />
      {errors.password && (
        <p className="field-error">{errors.password.message}</p>
      )}
      {registerMode && (
        <small className="muted">
          Mínimo 12 caracteres. No reutilices contraseñas.
        </small>
      )}
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting
          ? "Conectando…"
          : registerMode
            ? "Crear cuenta"
            : "Iniciar sesión"}
        <ArrowRight size={16} />
      </Button>
    </form>
  );
}
