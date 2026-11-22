import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createApi, publicApi, type Api } from './api';
import type { Profile, Token } from './types';

interface Session extends Token { user: Profile }
interface SessionContext { session: Session | null; api: Api; notice: string; establish: (token: Token) => Promise<Profile>; logout: () => Promise<void>; clear: (message?: string) => void }
const Context = createContext<SessionContext>(null!);
export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [notice, setNotice] = useState('');
  const clear = useCallback((message = '') => { setSession(null); setNotice(message); }, []);
  const expired = useCallback(() => clear('Votre session a expiré ou a été révoquée. Reconnectez-vous.'), [clear]);
  const api = useMemo(() => createApi(session?.access_token, expired), [session?.access_token, expired]);
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(expired, Math.max(0, Date.parse(session.expires_at) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [session, expired]);
  const establish = useCallback(async (token: Token) => {
    const user = await createApi(token.access_token).request<Profile>('/auth/me');
    setSession({ ...token, user }); setNotice(''); return user;
  }, []);
  const logout = useCallback(async () => { await api.request('/auth/logout', { method: 'POST' }); clear('Vous êtes déconnecté.'); }, [api, clear]);
  return <Context.Provider value={{ session, api: session ? api : publicApi, notice, establish, logout, clear }}>{children}</Context.Provider>;
}
export const useSession = () => useContext(Context);
