const SESSION_HINT_KEY = "cinerank.has_session";

type TokenListener = (token: string | null) => void;

const listeners = new Set<TokenListener>();
let memoryToken: string | null = null;
let revision = 0;

function notify(token: string | null): void {
  listeners.forEach((listener) => listener(token));
}

export const sessionHint = {
  get(): boolean {
    try {
      return window.localStorage.getItem(SESSION_HINT_KEY) === "1";
    } catch {
      return false;
    }
  },

  set(): void {
    try {
      window.localStorage.setItem(SESSION_HINT_KEY, "1");
    } catch {
      // A blocked storage area only prevents cross-reload restoration.
    }
  },

  clear(): void {
    try {
      window.localStorage.removeItem(SESSION_HINT_KEY);
    } catch {
      // Ignore storage failures; the in-memory reset is still correct.
    }
  },
};

export const tokenStore = {
  get(): string | null {
    return memoryToken;
  },

  set(token: string): void {
    memoryToken = token;
    revision += 1;
    sessionHint.set();
    notify(token);
  },

  clear(): void {
    memoryToken = null;
    revision += 1;
    sessionHint.clear();
    notify(null);
  },

  revision(): number {
    return revision;
  },

  subscribe(listener: TokenListener): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};
