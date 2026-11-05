import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button, Field, Input, toast } from "@/design/components";
import { ApiError } from "@/lib/api";

import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { passwordSchema } from "./PasswordFields";
import { FullPageLoading } from "./RequireAuth";

export default function ChangePasswordPage() {
  const { status, user, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = React.useState<string | null>(null);
  const schema = React.useMemo(
    () =>
      z
        .object({ current: z.string().min(1, "Enter your current password"), next: passwordSchema(user?.username), confirm: z.string() })
        .refine((v) => v.next === v.confirm, { path: ["confirm"], message: "Passwords do not match" })
        .refine((v) => v.next !== v.current, { path: ["next"], message: "Choose a different password" }),
    [user?.username],
  );
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { current: "", next: "", confirm: "" } });

  if (status === "loading") return <FullPageLoading />;
  if (status !== "authenticated" || !user) return <Navigate to="/login" replace />;

  const forced = user.must_change_password;
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      await changePassword(v.current, v.next);
      toast.success("Password changed");
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the password");
    }
  });

  return (
    <AuthLayout
      title={forced ? "Choose a new password" : "Change password"}
      subtitle={forced ? `Welcome, ${user.full_name}. Your administrator set a temporary password; replace it to continue.` : "Your other signed-in devices will be signed out."}
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {error && (
          <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">
            {error}
          </p>
        )}
        <Field label={forced ? "Temporary password" : "Current password"} htmlFor="current" error={form.formState.errors.current?.message}>
          <Input type="password" autoComplete="current-password" autoFocus {...form.register("current")} />
        </Field>
        <Field label="New password" htmlFor="next" hint="10+ characters, letters with digits or symbols" error={form.formState.errors.next?.message}>
          <Input type="password" autoComplete="new-password" {...form.register("next")} />
        </Field>
        <Field label="Confirm new password" htmlFor="confirm" error={form.formState.errors.confirm?.message}>
          <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          {!form.formState.isSubmitting && <KeyRound />}
          Change password
        </Button>
        {forced ? (
          <Button type="button" variant="ghost" className="w-full" onClick={() => void logout()}>
            Sign out instead
          </Button>
        ) : (
          <Button type="button" variant="ghost" className="w-full" onClick={() => navigate(-1)}>
            Cancel
          </Button>
        )}
      </form>
    </AuthLayout>
  );
}
