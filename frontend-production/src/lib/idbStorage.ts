import type { StateStorage } from 'zustand/middleware';

/**
 * Zustand persist storage adapter backed by IndexedDB with a localStorage
 * fallback. Writes are debounced and flushed on visibility change / unload
 * so large corpora can live in the browser without blocking the UI on every
 * keystroke.
 */

const STORE_NAME = 'kv';
const DEBOUNCE_MS = 1000;

type Kv = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
};

function openDb(dbName: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(dbName, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('indexedDB open failed'));
  });
}

function idbKv(dbName: string): Kv {
  let dbPromise: Promise<IDBDatabase> | null = null;
  const getDb = () => {
    if (!dbPromise) dbPromise = openDb(dbName);
    return dbPromise;
  };
  return {
    async getItem(key) {
      const db = await getDb();
      return new Promise<string | null>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).get(key);
        req.onsuccess = () => {
          const v = req.result;
          resolve(typeof v === 'string' ? v : v == null ? null : String(v));
        };
        req.onerror = () => reject(req.error);
      });
    },
    async setItem(key, value) {
      const db = await getDb();
      return new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    },
    async removeItem(key) {
      const db = await getDb();
      return new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    },
  };
}

function localStorageKv(): Kv {
  return {
    async getItem(key) {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    async setItem(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch {
        // storage full / disabled — swallow so persistence is best-effort
      }
    },
    async removeItem(key) {
      try {
        localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    },
  };
}

function chooseKv(dbName: string): Kv {
  if (typeof indexedDB !== 'undefined') {
    try {
      return idbKv(dbName);
    } catch {
      /* fall through */
    }
  }
  return localStorageKv();
}

/**
 * Build a zustand persist `StateStorage` that debounces writes and flushes
 * on tab hide / unload. Reads pass through unchanged; migration from the
 * legacy `production-queue` localStorage blob happens on first read.
 */
export function makeIdbStorage(dbName: string): StateStorage {
  const kv = chooseKv(dbName);
  const pending = new Map<string, string>();
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    const entries = [...pending.entries()];
    pending.clear();
    for (const [key, value] of entries) {
      void kv.setItem(key, value);
    }
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', flush);
    window.addEventListener('pagehide', flush);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush();
    });
  }

  return {
    async getItem(key) {
      const pendingVal = pending.get(key);
      if (pendingVal !== undefined) return pendingVal;
      const stored = await kv.getItem(key);
      if (stored != null) return stored;
      // One-shot migration read from the legacy localStorage blob.
      if (key === 'pypedeid-production:v2') {
        try {
          const legacy = localStorage.getItem('production-queue');
          if (legacy) return legacy;
        } catch {
          /* ignore */
        }
      }
      return null;
    },
    setItem(key, value) {
      pending.set(key, value);
      if (timer) clearTimeout(timer);
      timer = setTimeout(flush, DEBOUNCE_MS);
    },
    async removeItem(key) {
      pending.delete(key);
      await kv.removeItem(key);
    },
  };
}
