import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { CheckCircle2, ClipboardCheck, Download, FileText, History, RefreshCw, Save, Send, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { Badge, Empty, ErrorBox, Feedback, Field, Loading, Modal, PageHeading, dateTime, number } from '../components';
import { useAction, useLoad } from '../hooks';
import { useSession } from '../session';
import { useWorkspace } from '../workspace';
import { validateCounts, type Counts } from '../reportValidation';
import type { Candidate, ElectionStation, Report, ReportDocument, ReportEvent, Revision, Validation } from '../types';

export function NewReport() {
  const { data, electionId, reload } = useWorkspace();
  const { api } = useSession();
  const [selected, setSelected] = useState(electionId || data!.elections[0]?.id || '');
  const action = useAction();
  const navigate = useNavigate();
  const load = useLoad(signal => selected ? api.all<ElectionStation>(`/elections/${selected}/polling-stations`, signal) : Promise.resolve([]), [api, selected]);
  const existing = new Set(data!.reports.filter(r => r.election_id === selected).map(r => r.polling_station_id));
  const available = (load.data || []).filter(s => !existing.has(s.polling_station_id));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    action.run(async () => {
      const revision = await api.request<Revision>('/reports', { method: 'POST', body: { election_id: selected, polling_station_id: form.get('station') } });
      reload(); navigate(`/app/pv/${revision.report_id}`);
    }, '');
  }
  return <><Link className="back-link" to="/app/pv">Tous les procès-verbaux</Link><PageHeading eyebrow="SAISIE AGENT" title="Créer un procès-verbal" description="Sélectionnez un scrutin et un bureau qui vous est affecté." /><section className="panel narrow"><Feedback action={action} /><form onSubmit={submit} className="form-stack"><Field label="Scrutin"><select value={selected} required onChange={e => setSelected(e.target.value)}><option value="" disabled>Choisir un scrutin</option>{data!.elections.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></Field><ErrorBox message={load.error} retry={load.reload} />{load.loading ? <Loading /> : <Field label="Bureau affecté"><select name="station" required key={selected} defaultValue=""><option value="" disabled>Choisir un bureau</option>{available.map(s => <option key={s.polling_station_id} value={s.polling_station_id}>{data!.stations.find(row => row.id === s.polling_station_id)?.name}</option>)}</select></Field>}{!load.loading && !available.length && <p className="notice info">Aucun bureau disponible. Un PV existe déjà pour vos bureaux affectés, ou aucune affectation n’est définie.</p>}<p className="small-note">Un seul dossier est autorisé par bureau et par scrutin. Les corrections se font par nouvelle révision.</p><button className="button" disabled={action.busy || load.loading || Boolean(load.error) || !available.length}>Créer le brouillon</button></form></section></>;
}
function ResultsForm({ revision, candidates, saved, dirtyChanged }: { revision: Revision; candidates: Candidate[]; saved: () => void; dirtyChanged: (value: boolean) => void }) {
  const { api } = useSession();
  const action = useAction();
  const [dirty, setDirty] = useState(false);
  const [totals, setTotals] = useState<Counts>({ ...revision });
  const issue = validateCounts({ ...totals, results: candidates.map(c => ({ candidate_id: c.id, votes: totals.results.find(r => r.candidate_id === c.id)?.votes || 0 })) }, revision.registered_voters, revision.enforce_ballot_equation);
  function read(form: HTMLFormElement): Counts {
    const data = new FormData(form);
    return { ballots_cast: Number(data.get('ballots_cast')), valid_votes: Number(data.get('valid_votes')), blank_votes: Number(data.get('blank_votes')), invalid_votes: Number(data.get('invalid_votes')), results: candidates.map(c => ({ candidate_id: c.id, votes: Number(data.get(c.id)) })) };
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = read(event.currentTarget);
    const error = validateCounts(values, revision.registered_voters, revision.enforce_ballot_equation);
    if (error) { action.setError(error); return; }
    action.run(async () => { await api.request(`/reports/${revision.report_id}/revisions/${revision.revision_number}/results`, { method: 'PUT', body: { ...values, expected_version: revision.edit_version } }); setDirty(false); dirtyChanged(false); saved(); }, 'Résultats enregistrés. Vous pouvez maintenant soumettre le PV.');
  }
  return <form onSubmit={submit} onChange={event => { setDirty(true); dirtyChanged(true); setTotals(read(event.currentTarget)); }}><Feedback action={action} /><div className="panel-heading"><div><h2>Résultats du bureau</h2><p className="muted">{number(revision.registered_voters)} inscrits · Données fictives uniquement</p></div><span className="badge status-draft">{dirty ? 'Modifications non enregistrées' : 'Brouillon'}</span></div><div className="form-grid counts-grid">{[['ballots_cast', 'Bulletins déposés'], ['valid_votes', 'Suffrages exprimés'], ['blank_votes', 'Bulletins blancs'], ['invalid_votes', 'Bulletins nuls']].map(([key, label]) => <Field key={key} label={label}><input name={key} type="number" min={0} max={2147483647} step={1} required defaultValue={revision[key as keyof Counts] as number} /></Field>)}</div><h3 className="subheading">Répartition par liste candidate</h3><div className="candidate-inputs">{candidates.map((c, index) => <div className="candidate-input" key={c.id}><span className={`candidate-color c${index % 4}`} /><div><strong>{c.name}</strong><small>{c.code}</small></div><Field label={`Voix — ${c.name}`}><input name={c.id} type="number" min={0} max={2147483647} step={1} required defaultValue={revision.results.find(r => r.candidate_id === c.id)?.votes || 0} /></Field></div>)}</div><div className={`coherence ${issue ? 'warning' : ''}`}><CheckCircle2 size={20} /><span>{issue || 'Les totaux saisis sont cohérents.'}</span></div><div className="form-actions"><span className="muted">Enregistrez avant de soumettre.</span><button className="button" disabled={action.busy || !candidates.length}><Save size={17} />{action.busy ? 'Enregistrement…' : 'Enregistrer les résultats'}</button></div></form>;
}
function ResultsRead({ revision, candidates }: { revision: Revision; candidates: Candidate[] }) { return <><div className="panel-heading"><div><h2>Résultats structurés</h2><p className="muted">{number(revision.registered_voters)} inscrits au moment de la création.</p></div></div><div className="read-counts">{[['Bulletins déposés', revision.ballots_cast], ['Suffrages exprimés', revision.valid_votes], ['Blancs', revision.blank_votes], ['Nuls', revision.invalid_votes]].map(([label, value]) => <div key={label}><small>{label}</small><strong>{number(Number(value))}</strong></div>)}</div><div className="results-list">{revision.results.map((r, index) => <div key={r.candidate_id}><div className="result-label"><span><i className={`candidate-color c${index % 4}`} />{candidates.find(c => c.id === r.candidate_id)?.name || 'Liste candidate'}</span><strong>{number(r.votes)} <small>voix</small></strong></div><div className="result-track"><span className={`c${index % 4}`} style={{ width: `${revision.valid_votes ? r.votes / revision.valid_votes * 100 : 0}%` }} /></div></div>)}</div>{!revision.results.length && <Empty title="Résultats non renseignés" />}</>; }
function Documents({ reportId, revision, documents, editable, refresh }: { reportId: string; revision: Revision; documents: ReportDocument[]; editable: boolean; refresh: () => void }) {
  const { api } = useSession(); const action = useAction();
  const base = `/reports/${reportId}/revisions/${revision.revision_number}/documents`;
  function upload(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; const input = form.elements.namedItem('document') as HTMLInputElement; const file = input.files?.[0]; if (!file) { action.setError('Sélectionnez un fichier.'); return; } const data = new FormData(); data.append('expected_version', String(revision.edit_version)); data.append('file', file); action.run(async () => { await api.request(base, { method: 'POST', body: data }); form.reset(); refresh(); }, 'Pièce justificative déposée dans le stockage privé.'); }
  function remove(id: string) { if (!window.confirm('Supprimer cette pièce justificative ?')) return; action.run(async () => { await api.request(`${base}/${id}`, { method: 'DELETE' }); refresh(); }, 'Pièce supprimée.'); }
  function download(document: ReportDocument) { action.run(async () => { const blob = await api.download(`${base}/${document.id}/content`); const url = URL.createObjectURL(blob); const anchor = window.document.createElement('a'); anchor.href = url; anchor.download = document.original_filename; anchor.click(); URL.revokeObjectURL(url); }, 'Téléchargement préparé.'); }
  return <section className="panel documents-panel"><div className="panel-heading"><div><h2 className="icon-heading"><FileText size={19} />Pièces justificatives</h2><p className="muted">Documents privés · PDF, JPEG ou PNG · 10 Mo maximum</p></div><span className="badge">{documents.length} fichier{documents.length !== 1 ? 's' : ''}</span></div><Feedback action={action} />{documents.length ? <div className="document-list">{documents.map(document => <article key={document.id} className="document-row"><FileText size={20} /><div><strong>{document.original_filename}</strong><small>{(document.size_bytes / 1024).toFixed(1)} Ko · {document.storage_provider === 'S3' ? 'Amazon S3' : 'Stockage local'} · {document.processing_status}</small></div><div className="button-row"><button className="icon-button" title="Télécharger" disabled={action.busy} onClick={() => download(document)}><Download size={17} /></button>{editable && <button className="icon-button danger-outline" title="Supprimer" disabled={action.busy} onClick={() => remove(document.id)}><Trash2 size={17} /></button>}</div></article>)}</div> : <Empty title="Aucune pièce justificative">{editable ? 'Ajoutez le PV scanné avant de soumettre le dossier.' : 'Aucun document n’est associé à cette révision.'}</Empty>}{editable && <form onSubmit={upload} className="upload-form"><Field label="PV scanné ou photographié"><input name="document" type="file" required accept="application/pdf,image/jpeg,image/png" /></Field><button className="button secondary" disabled={action.busy}><Upload size={17} />Déposer la pièce</button></form>}</section>;
}
const eventLabels: Record<string, string> = { CREATED: 'Brouillon créé', RESULTS_UPDATED: 'Résultats enregistrés', SUBMITTED: 'PV soumis', REVISED: 'Nouvelle révision', REVIEW_STARTED: 'Vérification démarrée', APPROVED: 'PV approuvé', REJECTED: 'PV rejeté' };
export function ReportDetail() {
  const { id } = useParams();
  const { api, session } = useSession();
  const workspace = useWorkspace();
  const action = useAction();
  const [selected, setSelected] = useState<number>();
  const [decision, setDecision] = useState<'submit' | 'revise' | 'APPROVED' | 'REJECTED' | null>(null);
  const [dirty, setDirty] = useState(false);
  const load = useLoad(async signal => {
    const report = await api.request<Report>(`/reports/${id}`, { signal });
    const [revisions, history, validations, members] = await Promise.all([api.all<Revision>(`/reports/${id}/revisions`, signal), api.all<ReportEvent>(`/reports/${id}/history`, signal), api.all<Validation>(`/reports/${id}/validations`, signal), api.all<{ candidate_id: string }>(`/elections/${report.election_id}/candidates`, signal)]);
    const documents = (await Promise.all(revisions.map(revision => api.request<ReportDocument[]>(`/reports/${id}/revisions/${revision.revision_number}/documents`, { signal })))).flat();
    return { report, revisions, history, validations, members, documents };
  }, [api, id]);
  useEffect(() => { setSelected(undefined); setDirty(false); }, [id]);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    const click = (e: MouseEvent) => { const anchor = (e.target as Element).closest('a'); if (anchor && anchor.pathname !== location.pathname && !window.confirm('Les résultats ne sont pas enregistrés. Quitter ce dossier ?')) { e.preventDefault(); e.stopPropagation(); } };
    window.addEventListener('beforeunload', beforeUnload); document.addEventListener('click', click, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', click, true); };
  }, [dirty]);
  if (!load.data) return <><ErrorBox message={load.error} retry={load.reload} />{load.loading && <Loading />}</>;
  const { report, revisions, history, validations, members, documents } = load.data;
  const revision = revisions.find(r => r.revision_number === (selected || report.current_revision))!;
  const current = revision.revision_number === report.current_revision;
  const station = workspace.data!.stations.find(s => s.id === report.polling_station_id);
  const election = workspace.data!.elections.find(e => e.id === report.election_id);
  const candidates = workspace.data!.candidates.filter(c => members.some(m => m.candidate_id === c.id));
  const editable = current && revision.status === 'DRAFT' && session!.user.role === 'AGENT';
  const canValidate = current && session!.user.role === 'VALIDATOR' && report.created_by !== session!.user.id;
  const base = `/reports/${report.id}/revisions/${revision.revision_number}`;
  function refresh() { load.reload(); workspace.reload(); }
  function reload() { if (!dirty || window.confirm('Recharger et abandonner les modifications non enregistrées ?')) { setDirty(false); load.reload(); } }
  function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const reason = String(new FormData(event.currentTarget).get('reason') || '').trim();
    if ((decision === 'REJECTED' || decision === 'revise') && !reason) { action.setError('Un motif est obligatoire.'); return; }
    action.run(async () => {
      const route = decision === 'submit' || decision === 'revise' ? decision : 'decision';
      const body = decision === 'submit' ? {} : decision === 'revise' ? { reason } : { decision, reason };
      await api.request<Revision>(`${base}/${route}`, { method: 'POST', body: { ...body, expected_version: revision.edit_version } });
      setDecision(null); setSelected(undefined); refresh();
    }, 'Action enregistrée dans l’historique du dossier.');
  }
  return <><Link className="back-link" to="/app/pv">Tous les procès-verbaux</Link><PageHeading eyebrow={`${station?.code || 'DOSSIER PV'} · ${election?.name || ''}`} title={station?.name || 'Dossier PV'} description={`Révision ${revision.revision_number} · Créé le ${dateTime(report.created_at)}`}><Badge status={revision.status} /><button className="button secondary" disabled={load.loading} onClick={reload}><RefreshCw size={16} />Recharger</button></PageHeading><ErrorBox message={load.error} retry={reload} /><Feedback action={action} />
    <div className="report-layout"><div><section className="panel">{editable ? <ResultsForm key={`${id}-${revision.id}-${revision.edit_version}`} revision={revision} candidates={candidates} saved={refresh} dirtyChanged={setDirty} /> : <ResultsRead revision={revision} candidates={workspace.data!.candidates} />}</section><Documents reportId={report.id} revision={revision} documents={documents.filter(document => document.revision_id === revision.id)} editable={editable} refresh={refresh} />
    {current && <section className="panel workflow-panel"><h2>Action sur le dossier</h2>{editable && <><p>La soumission transmet cette révision au circuit de vérification. Les résultats ne seront plus modifiables directement.</p><button className="button" disabled={dirty || !revision.results.length || action.busy} onClick={() => { action.reset(); setDecision('submit'); }}><Send size={17} />Soumettre le PV</button>{dirty && <p className="small-note">Enregistrez les modifications avant de soumettre.</p>}</>}
    {canValidate && revision.status === 'SUBMITTED' && <><p>Commencez la revue pour vérifier les totaux et préparer votre décision.</p><button className="button" disabled={action.busy} onClick={() => action.run(async () => { await api.request(`${base}/review`, { method: 'POST', body: { expected_version: revision.edit_version } }); refresh(); }, 'La vérification a commencé.')}><ClipboardCheck size={17} />Commencer la vérification</button></>}
    {canValidate && revision.status === 'PENDING_VALIDATION' && <><p>Votre décision est conservée dans l’historique. Un rejet doit être motivé.</p><div className="button-row"><button className="button" disabled={action.busy} onClick={() => { action.reset(); setDecision('APPROVED'); }}><CheckCircle2 size={17} />Approuver le PV</button><button className="button danger-outline" disabled={action.busy} onClick={() => { action.reset(); setDecision('REJECTED'); }}>Rejeter le PV</button></div></>}
    {session!.user.role === 'AGENT' && ['SUBMITTED', 'REJECTED', 'PROCESSING_FAILED'].includes(revision.status) && <><p>Une correction crée un nouveau brouillon et conserve cette révision.</p><button className="button secondary" onClick={() => { action.reset(); setDecision('revise'); }}>Créer une correction</button></>}
    {(session!.user.role === 'ADMIN' || ['APPROVED', 'PUBLISHED'].includes(revision.status) || (session!.user.role === 'AGENT' && revision.status === 'PENDING_VALIDATION')) && <p className="notice info"><ShieldCheck size={18} />{revision.status === 'APPROVED' ? 'Ce PV est approuvé. Il n’est pas publié sur un tableau de bord public.' : 'Ce dossier est en lecture seule pour votre rôle dans son état actuel.'}</p>}</section>}
    {validations.length > 0 && <section className="panel"><h2>Décisions de validation</h2>{validations.map(v => <article className="decision-card" key={v.id}><Badge status={v.decision as 'APPROVED' | 'REJECTED'} /><small>{dateTime(v.created_at)} · Révision {revisions.find(r => r.id === v.revision_id)?.revision_number}</small><p>{v.reason || 'Approbation des résultats structurés.'}</p></article>)}</section>}</div>
    <aside><section className="panel"><h2>Versions du dossier</h2><Field label="Révision consultée"><select value={revision.revision_number} onChange={e => { if (!dirty || window.confirm('Abandonner les modifications non enregistrées ?')) { setDirty(false); setSelected(Number(e.target.value)); } }}>{revisions.map(r => <option key={r.id} value={r.revision_number}>Révision {r.revision_number}{r.revision_number === report.current_revision ? ' · courante' : ''}</option>)}</select></Field>{revision.revision_reason && <p className="small-note">Motif : {revision.revision_reason}</p>}{!current && <p className="notice info">Version historique en lecture seule.</p>}</section><section className="panel"><h2 className="icon-heading"><History size={19} />Historique du dossier</h2><ol className="timeline">{[...history].reverse().map(event => <li key={event.id}><strong>{eventLabels[event.action] || event.action}</strong><small>{dateTime(event.created_at)} · V{revisions.find(r => r.id === event.revision_id)?.revision_number}</small>{event.note && <p>{event.note}</p>}</li>)}</ol></section></aside></div>
    {decision && <Modal title={decision === 'submit' ? 'Soumettre ce procès-verbal ?' : decision === 'revise' ? 'Créer une nouvelle révision' : decision === 'APPROVED' ? 'Approuver ce procès-verbal ?' : 'Motiver le rejet'} close={() => setDecision(null)} busy={action.busy}><form onSubmit={decide} className="form-stack"><p>{decision === 'APPROVED' ? 'Vous confirmez avoir vérifié les résultats structurés. Cette décision sera enregistrée et ne publiera pas les résultats.' : decision === 'submit' ? 'Cette version sera transmise aux validateurs. Vérifiez les totaux avant de confirmer.' : 'Décrivez les éléments à corriger. Le motif sera conservé dans l’historique.'}</p>{decision !== 'submit' && <Field label={decision === 'APPROVED' ? 'Note de validation (facultative)' : 'Motif obligatoire'}><textarea name="reason" required={decision !== 'APPROVED'} maxLength={1000} rows={4} /></Field>}<Feedback action={action} /><div className="form-actions"><button type="button" className="button secondary" disabled={action.busy} onClick={() => setDecision(null)}>Annuler</button><button className={`button ${decision === 'REJECTED' ? 'danger' : ''}`} disabled={action.busy}>{action.busy ? 'Enregistrement…' : 'Confirmer'}</button></div></form></Modal>}
  </>;
}
