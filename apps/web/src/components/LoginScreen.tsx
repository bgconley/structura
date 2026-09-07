import type {PasswordCredentials} from "../useSession";

export function LoginScreen({
  error,
  message,
  submitting,
  onSubmit,
}: {
  error: string | null;
  message: string | null;
  submitting: boolean;
  onSubmit: (credentials: PasswordCredentials) => Promise<void>;
}) {
  return (
    <main className="login-screen">
      <section className="login-card">
        <span className="logo-mark" />
        <h1>Structura</h1>
        <p>Sign in to open the local-first evidence workbench.</p>
        {message ? <p role="status">{message}</p> : null}
        <form aria-busy={submitting} onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void onSubmit({email: String(data.get("email") ?? ""), password: String(data.get("password") ?? "")});
        }}>
          <label>
            Email
            <input name="email" type="email" required autoComplete="username" autoFocus disabled={submitting} />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
              disabled={submitting}
            />
          </label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button type="submit" disabled={submitting}>{submitting ? "Signing in..." : "Sign in"}</button>
        </form>
      </section>
    </main>
  );
}
