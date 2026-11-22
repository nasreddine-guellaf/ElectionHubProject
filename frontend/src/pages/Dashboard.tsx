import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, ClipboardCheck, Clock3, FileText, Plus, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { Badge, Empty, PageHeading, date, number, statusLabels } from '../components';
import { useSession } from '../session';
import { useWorkspace } from '../workspace';
import type { ReportRow, Status } from '../types';

export function ReportTable({ reports, compact = false }: { reports: ReportRow[]; compact?: boolean }) {
  const { data } = useWorkspace();
  if (!reports.length) return <Empty title="Aucun procès-verbal à afficher">Les dossiers de votre périmètre apparaîtront ici.</Empty>;
  return <div className="table-scroll"><table><thead><tr><th>Bureau de vote</th>{!compact && <th>Scrutin</th>}<th>Statut</th><th>Révision</th><th>Création</th><th><span className="sr-only">Consulter</span></th></tr></thead><tbody>{reports.map(report => {
    const station = data!.stations.find(s => s.id === report.polling_station_id);
    return <tr key={report.id}><td><span className="table-title">{station?.name || 'Bureau non disponible'}</span><span className="table-sub">{station?.code}</span></td>{!compact && <td className="cell-wrap">{data!.elections.find(e => e.id === report.election_id)?.name}</td>}<td><Badge status={report.revision.status} /></td><td><span className="revision-chip">V{report.current_revision}</span></td><td className="nowrap muted">{date(report.created_at)}</td><td><Link className="table-link" to={`/app/pv/${report.id}`} aria-label={`Consulter le PV de ${station?.name || report.id}`}>Consulter</Link></td></tr>;
  })}</tbody></table></div>;
}
export function Dashboard() {
  const { session } = useSession();
  const { data, electionId, reload, loading } = useWorkspace();
  const reports = data!.reports.filter(r => !electionId || r.election_id === electionId);
  const counts = (statuses: Status[]) => reports.filter(r => statuses.includes(r.revision.status)).length;
  const waiting = counts(['SUBMITTED', 'PENDING_VALIDATION']);
  const approved = counts(['APPROVED']);
  const needsWork = counts(['DRAFT', 'REJECTED', 'PROCESSING_FAILED']);
  const distribution: [string, number, string][] = [['À préparer / corriger', needsWork, 'slate'], ['En attente de validation', waiting, 'amber'], ['Approuvés', approved, 'teal']];
  const role = session!.user.role;
  const recent = [...reports].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const priority = reports.filter(r => (role === 'AGENT' ? ['DRAFT', 'REJECTED', 'PROCESSING_FAILED'] : ['SUBMITTED', 'PENDING_VALIDATION']).includes(r.revision.status));
  return <><PageHeading eyebrow="SUIVI DES OPÉRATIONS" title="Vue d’ensemble" description="Suivez l’avancement des procès-verbaux, du dépôt à la validation."><button className="button secondary" disabled={loading} onClick={reload}><RefreshCw size={16} className={loading ? 'spin' : ''} />Actualiser</button>{role === 'AGENT' && <Link to="/app/pv/nouveau" className="button"><Plus size={18} />Nouveau PV</Link>}</PageHeading>
    <div className="welcome-banner"><div><span className="eyebrow">UN SUIVI PARTAGÉ, DES RÔLES DÉFINIS</span><h2>Des résultats vérifiés à chaque étape.</h2><p>{role === 'AGENT' ? 'Préparez vos PV et suivez leur examen par les validateurs.' : role === 'VALIDATOR' ? 'Examinez les résultats soumis et consignez chaque décision.' : 'Supervisez les dossiers et gérez les accès de votre équipe.'}</p></div><div className="banner-symbol" aria-hidden="true"><ShieldCheck size={65} strokeWidth={1.2} /></div></div>
    <div className="stats-grid">{[{ label: 'Procès-verbaux', count: reports.length, help: 'Dans votre périmètre', Icon: FileText, color: 'blue' }, { label: 'À vérifier', count: waiting, help: 'Soumis ou en vérification', Icon: Clock3, color: 'amber' }, { label: 'Approuvés', count: approved, help: 'Validation humaine terminée', Icon: CheckCircle2, color: 'teal' }, { label: 'À préparer / corriger', count: needsWork, help: 'Brouillons ou retours', Icon: ClipboardCheck, color: 'purple' }].map(({ label, count, help, Icon, color }) => <article className="stat-card" key={label}><div className="stat-top"><span>{label}</span><span className={`stat-icon ${color}`}><Icon size={19} /></span></div><strong>{number(count)}</strong><small>{help}</small></article>)}</div>
    <div className="dashboard-grid"><section className="panel table-panel"><div className="panel-heading"><div><h2>Derniers procès-verbaux</h2><p className="muted">Les dossiers les plus récemment créés.</p></div><Link className="text-button" to="/app/pv">Tout consulter</Link></div><ReportTable reports={recent.slice(0, 5)} compact /></section><section className="panel progression"><h2>Avancement des dossiers</h2><p className="muted">Révisions courantes uniquement.</p><div className="progress-total"><strong>{reports.length ? Math.round(approved / reports.length * 100) : 0}<span>%</span></strong><span>de PV approuvés</span></div><div className="stacked-bar" aria-label={`${approved} PV approuvés sur ${reports.length}`}>{distribution.map(([label, count, color]) => <span key={label} className={color} style={{ width: `${reports.length ? count / reports.length * 100 : 0}%` }} />)}</div><div className="legend">{distribution.map(([label, count, color]) => <div key={label}><span className={`legend-swatch ${color}`} /><span>{label}</span><strong>{count}</strong></div>)}</div><p className="small-note">L’approbation ne déclenche pas de publication publique.</p></section></div>
    <section className="panel attention-panel"><div className="panel-heading"><div><h2>{role === 'AGENT' ? 'Vos prochaines actions' : 'Dossiers à examiner'}</h2><p className="muted">{role === 'ADMIN' ? 'Les décisions restent réservées aux validateurs.' : 'Retrouvez les dossiers qui nécessitent votre attention.'}</p></div><span className="count-pill">{priority.length}</span></div>{priority.length ? <div className="action-rows">{priority.slice(0, 3).map(r => <Link key={r.id} to={`/app/pv/${r.id}`}><span className="row-icon"><FileText size={19} /></span><span><strong>{data!.stations.find(s => s.id === r.polling_station_id)?.name}</strong><small>{statusLabels[r.revision.status]} · Révision {r.current_revision}</small></span><span className="table-link">Ouvrir le dossier</span></Link>)}</div> : <div className="all-clear"><CheckCircle2 size={21} />Aucun dossier en attente dans cette sélection.</div>}</section>
  </>;
}
export function ReportsPage() {
  const { data, electionId, loading, reload } = useWorkspace();
  const { session } = useSession();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(0);
  const filtered = data!.reports.filter(r => {
    const station = data!.stations.find(s => s.id === r.polling_station_id);
    return (!electionId || r.election_id === electionId) && (!status || r.revision.status === status) && `${station?.name} ${station?.code}`.toLowerCase().includes(search.toLowerCase());
  });
  const current = Math.min(page, Math.max(0, Math.ceil(filtered.length / 10) - 1));
  return <><PageHeading eyebrow="DOSSIERS ÉLECTORAUX" title={session!.user.role === 'VALIDATOR' ? 'Validation des procès-verbaux' : 'Procès-verbaux'} description="Consultez les résultats structurés, les révisions et les décisions.">{session!.user.role === 'AGENT' && <Link to="/app/pv/nouveau" className="button"><Plus size={18} />Nouveau PV</Link>}</PageHeading><section className="panel table-panel"><div className="table-toolbar"><label className="search-field"><Search size={18} /><span className="sr-only">Rechercher un procès-verbal</span><input type="search" placeholder="Rechercher un bureau…" value={search} onChange={e => { setSearch(e.target.value); setPage(0); }} /></label><label><span className="sr-only">Statut du PV</span><select value={status} onChange={e => { setStatus(e.target.value); setPage(0); }}><option value="">Tous les statuts</option>{Object.entries(statusLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button className="icon-button" disabled={loading} onClick={reload} aria-label="Actualiser les PV"><RefreshCw size={18} /></button></div><ReportTable reports={filtered.slice(current * 10, current * 10 + 10)} /><div className="pagination"><span>{filtered.length} dossier(s)</span><div><button className="button secondary small-button" disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button><span>{current + 1} / {Math.max(1, Math.ceil(filtered.length / 10))}</span><button className="button secondary small-button" disabled={(current + 1) * 10 >= filtered.length} onClick={() => setPage(current + 1)}>Suivant</button></div></div></section></>;
}
