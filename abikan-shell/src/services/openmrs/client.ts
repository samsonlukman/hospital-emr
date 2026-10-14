export class OpenmrsRequestError extends Error {
  status?: number;
  body?: string;

  constructor(message: string, status?: number, body?: string) {
    super(message);
    this.name = "OpenmrsRequestError";
    this.status = status;
    this.body = body;
  }
}

export function messageFromOpenmrsBody(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body) as {
      error?: {
        message?: string;
        detail?: string;
        globalErrors?: Array<{ message?: string }>;
      };
      message?: string;
    };
    const global = parsed.error?.globalErrors
      ?.map((item) => item.message)
      .filter(Boolean)
      .join(" ");
    const message =
      parsed.error?.message || global || parsed.message || parsed.error?.detail;
    if (message) {
      return message;
    }
  } catch {
    if (body && body.length < 400 && !body.trim().startsWith("<")) {
      return body;
    }
  }
  if (/encounter datetime should be before the current date/i.test(body)) {
    return "The consultation time was ahead of the hospital clock. Save again.";
  }
  return `Request failed with status ${status}`;
}

async function openmrsFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 401) {
    throw new OpenmrsRequestError("unauthenticated", 401);
  }

  return response;
}

export async function openmrsGet<T>(path: string): Promise<T> {
  const response = await openmrsFetch(path);
  if (!response.ok) {
    const body = await response.text();
    throw new OpenmrsRequestError(
      messageFromOpenmrsBody(response.status, body),
      response.status,
      body,
    );
  }
  return (await response.json()) as T;
}

export async function openmrsPost<T>(path: string, body: unknown): Promise<T> {
  const response = await openmrsFetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new OpenmrsRequestError(
      messageFromOpenmrsBody(response.status, text),
      response.status,
      text,
    );
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : {}) as T;
}

export async function openmrsDelete(path: string): Promise<void> {
  const response = await openmrsFetch(path, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    throw new OpenmrsRequestError(
      `Request failed with status ${response.status}`,
      response.status,
    );
  }
}

export function getCookie(name: string): string | null {
  const prefix = `${name}=`;
  const parts = document.cookie.split(";").map((part) => part.trim());
  const match = parts.find((part) => part.startsWith(prefix));
  if (!match) {
    return null;
  }
  return decodeURIComponent(match.slice(prefix.length));
}

export function setCookie(name: string, value: string, days = 7): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  const maxAge = days * 24 * 60 * 60;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; SameSite=Lax${secure}`;
}

export function clearCookie(name: string): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax${secure}`;
}
