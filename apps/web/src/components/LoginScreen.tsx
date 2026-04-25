import type {FormEvent} from "react";

export function LoginScreen({
  error,
  onSubmit,
}: {
  error: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <main className="login-screen">
      <section className="login-card">
        <span className="logo-mark" />
        <h1>Structura</h1>
        <p>Sign in to open the local-first evidence workbench.</p>
        <form onSubmit={onSubmit}>
          <label>
            Email
            <input name="email" type="email" required autoComplete="email" />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button type="submit">Sign in</button>
        </form>
      </section>
    </main>
  );
}
