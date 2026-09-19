const CSRF_COOKIE_NAME = "resourceplanner_csrf";

export function csrfToken(): string | null {
  if (typeof document === "undefined") return null;
  for (const part of document.cookie.split(";")) {
    const [rawName, ...rawValue] = part.trim().split("=");
    if (decodeURIComponent(rawName) !== CSRF_COOKIE_NAME) continue;
    return decodeURIComponent(rawValue.join("="));
  }
  return null;
}

export function csrfHeaders(): Record<string, string> {
  const token = csrfToken();
  return token ? { "X-CSRF-Token": token } : {};
}
