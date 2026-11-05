import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, LogIn } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { Button, Field, Input } from "@/design/components";
import { ApiError } from "@/lib/api";

import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { FullPageLoading } from "./RequireAuth";

const schema = z.object({
  username: z.string().trim().min(1, "Enter your username"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

/** Only allow in-app redirects after sign-in (no open redirects). */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export default function LoginPage() {
  const { status, user, login, notice } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = React.useState<string | null>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { username: "", password: "" } });

  if (status === "loading") return <FullPageLoading />;
  if (status === "setup") return <Navigate to="/setup" replace />;
  if (status === "authenticated" && user) return <Navigate to={user.must_change_password ? "/change-password" : safeNext(params.get("next"))} replace />;

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const me = await login(values.username, values.password);
      navigate(me.must_change_password ? "/change-password" : safeNext(params.get("next")), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed");
      form.setValue("password", "");
      form.setFocus("password");
    }
  });

  const shown = error ?? notice;
  return (
    <AuthLayout title="Sign in" subtitle="Use the account your administrator created for you.">
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {shown && (
          <div role="alert" className="flex gap-2 rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{shown}</span>
          </div>
        )}
        <Field label="Username" htmlFor="username" error={form.formState.errors.username?.message}>
          <Input autoComplete="username" autoFocus autoCapitalize="none" spellCheck={false} {...form.register("username")} />
        </Field>
        <Field label="Password" htmlFor="password" error={form.formState.errors.password?.message}>
          <Input type="password" autoComplete="current-password" {...form.register("password")} />
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          {!form.formState.isSubmitting && <LogIn />}
          Sign in
        </Button>
        <p className="text-center text-xs text-neutral-500">Forgotten your password? Ask an administrator to reset it.</p>
      </form>
    </AuthLayout>
  );
}
