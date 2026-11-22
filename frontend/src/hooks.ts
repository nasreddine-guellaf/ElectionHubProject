import { useEffect, useState, type DependencyList } from 'react';
import { errorMessage } from './api';

export function useLoad<T>(loader: (signal: AbortSignal) => Promise<T>, dependencies: DependencyList) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    loader(controller.signal).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [...dependencies, version]);
  return { data, loading, error, reload: () => setVersion(v => v + 1) };
}
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  async function run(action: () => Promise<void>, message = 'Modification enregistrée.') {
    if (busy) return;
    setBusy(true); setError(''); setSuccess('');
    try { await action(); setSuccess(message); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return { busy, error, success, run, setError, reset: () => { setError(''); setSuccess(''); } };
}
