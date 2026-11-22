import type { Page } from './types';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError'; }
}
export function createApi(token?: string, expired?: () => void) {
  async function request<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
    let response: Response;
    const multipart = options.body instanceof FormData;
    let requestBody: BodyInit | undefined;
    if (options.body !== undefined) requestBody = options.body instanceof FormData ? options.body : JSON.stringify(options.body);
    try {
      response = await fetch('/api/v1' + path, {
        method: options.method || 'GET', cache: 'no-store', credentials: 'omit',
        signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
        headers: { Accept: 'application/json', ...(options.body !== undefined && !multipart ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: requestBody,
      });
    } catch (error) {
      if (options.signal?.aborted) throw error;
      throw new ApiError(0, 'Connexion au serveur impossible. Vérifiez votre connexion puis réessayez.');
    }
    if (response.status === 204) return undefined as T;
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && token) expired?.();
      let message = typeof body?.detail === 'string' ? body.detail : 'La demande a échoué. Réessayez.';
      if (response.status === 429) message = `Trop de tentatives. Réessayez dans ${Math.ceil(Number(response.headers.get('Retry-After') || 60) / 60)} minute(s).`;
      throw new ApiError(response.status, message);
    }
    if (body === null) throw new ApiError(0, 'Réponse du serveur illisible. Réessayez.');
    return body as T;
  }
  async function all<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const result: T[] = [];
    let offset = 0;
    for (;;) {
      const page = await request<Page<T>>(`${path}${path.includes('?') ? '&' : '?'}limit=100&offset=${offset}`, { signal });
      result.push(...page.items);
      offset += page.items.length;
      if (offset >= page.total || !page.items.length) return result;
    }
  }
  async function download(path: string): Promise<Blob> {
    let response: Response;
    try {
      response = await fetch('/api/v1' + path, {
        cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(15000),
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
    } catch {
      throw new ApiError(0, 'Téléchargement impossible. Vérifiez votre connexion puis réessayez.');
    }
    if (!response.ok) {
      if (response.status === 401 && token) expired?.();
      const body = await response.json().catch(() => null);
      throw new ApiError(response.status, typeof body?.detail === 'string' ? body.detail : 'Téléchargement impossible.');
    }
    return response.blob();
  }
  return { request, all, download };
}
export type Api = ReturnType<typeof createApi>;
export const publicApi = createApi();
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Une erreur est survenue.';
