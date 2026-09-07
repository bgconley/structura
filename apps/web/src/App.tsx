import {AuthenticatedApp} from "./AuthenticatedApp";
import {LoginScreen} from "./components/LoginScreen";
import {useSession} from "./useSession";

export default function App() {
  const auth = useSession();
  if (auth.phase === "authenticated" && auth.session) {
    return <AuthenticatedApp key={auth.generation} session={auth.session}
      onSignOut={auth.signOut} sessionError={auth.error} />;
  }
  if (auth.phase === "anonymous") {
    return <LoginScreen error={auth.error} message={auth.message}
      submitting={auth.submitting} onSubmit={auth.signIn} />;
  }
  const signingOut = auth.phase === "signing-out";
  const failedSignOut = auth.phase === "sign-out-failed";
  return (
    <main className="login-screen">
      <section className="login-card" aria-busy={auth.phase === "checking" || signingOut}>
        <span className="logo-mark" />
        <h1>Structura</h1>
        <p role="status">{auth.error ?? (signingOut ? "Signing out..." : "Checking your session...")}</p>
        {auth.phase === "unavailable" || failedSignOut ? (
          <button className="command-button" type="button"
            onClick={() => void (failedSignOut ? auth.signOut() : auth.retry())}>
            {failedSignOut ? "Try signing out again" : "Retry connection"}
          </button>
        ) : null}
      </section>
    </main>
  );
}
