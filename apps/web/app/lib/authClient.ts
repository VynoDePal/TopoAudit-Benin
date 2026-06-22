// Helpers d'authentification côté client (P0). Le token JWT (obtenu via /api/auth/login
// ou /api/auth/register) est ajouté en en-tête Authorization: Bearer sur tous les appels
// API. En mode démo local (backend DEMO_LOCAL), l'absence de token reste acceptée.

export function authHeaders(token: string | null | undefined): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Fusionne des en-têtes de base avec l'en-tête d'auth (si token présent).
export function withAuth(
  token: string | null | undefined,
  base?: Record<string, string>,
): Record<string, string> {
  return { ...(base ?? {}), ...authHeaders(token) };
}

const TOKEN_KEY = "topoaudit_token";

export function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* localStorage indisponible : on garde le token en mémoire uniquement */
  }
}
