import { createContext, useContext, useState, type ReactNode } from 'react';
import { useLoad } from './hooks';
import { useSession } from './session';
import type { Assignment, Candidate, Election, Report, ReportRow, Revision, Station } from './types';

interface Data { elections: Election[]; stations: Station[]; candidates: Candidate[]; assignments: Assignment[]; reports: ReportRow[] }
interface Workspace { data?: Data; error: string; loading: boolean; reload: () => void; electionId: string; setElectionId: (id: string) => void }
const Context = createContext<Workspace>(null!);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { api } = useSession();
  const [electionId, setElectionId] = useState('');
  const load = useLoad(async signal => {
    const [elections, stations, candidates, assignments, reports] = await Promise.all([
      api.all<Election>('/elections', signal), api.all<Station>('/polling-stations', signal),
      api.all<Candidate>('/candidates', signal), api.all<Assignment>('/assignments', signal), api.all<Report>('/reports', signal),
    ]);
    const rows = await Promise.all(reports.map(async report => ({ ...report, revision: await api.request<Revision>(`/reports/${report.id}/revisions/${report.current_revision}`, { signal }) })));
    return { elections, stations, candidates, assignments, reports: rows };
  }, [api]);
  return <Context.Provider value={{ ...load, electionId, setElectionId }}>{children}</Context.Provider>;
}
export const useWorkspace = () => useContext(Context);
