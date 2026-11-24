import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import { createApi } from '../api';
import { validateCounts } from '../reportValidation';
import type { Incident, ReportDocument, Revision, Role } from '../types';

const station = { id: 'station-1', code: 'DEMO-BV-001', name: 'Bureau fictif des Nuages', registered_voters: 100 };
const election = { id: 'election-1', code: 'DEMO-ELECTION', name: 'Scrutin fictif', start_date: '2026-11-01', end_date: '2026-11-01', enforce_ballot_equation: true };
const candidate = { id: 'candidate-1', name: 'Liste Aurore', code: 'DEMO-LISTE-A' };
const baseRevision: Revision = { id: 'revision-1', report_id: 'report-1', election_id: election.id, revision_number: 1, status: 'DRAFT', edit_version: 1, created_by: 'agent', revision_reason: '', registered_voters: 100, enforce_ballot_equation: true, ballots_cast: 0, valid_votes: 0, blank_votes: 0, invalid_votes: 0, results: [], created_at: '2026-11-21T10:00:00Z', submitted_at: null };
let revision: Revision;
let reportExists: boolean;
let calls: { path: string; method: string; body: any }[];
let otpDisabled: boolean;
let forceConflict: boolean;
let failReports: number;
let documents: ReportDocument[];
let incidents: Incident[];
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const userFor = (role: Role) => ({ id: role.toLowerCase(), display_name: `${role} fictif`, role });
beforeEach(() => {
  revision = structuredClone(baseRevision); reportExists = true; calls = []; otpDisabled = false; forceConflict = false; failReports = 0; documents = []; incidents = [];
  window.localStorage.clear(); window.sessionStorage.clear();
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const url = new URL(input, 'http://localhost'); const path = url.pathname.replace('/api/v1', ''); const method = options.method || 'GET';
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
    calls.push({ path, method, body });
    const authorization = (options.headers as Record<string, string>)?.Authorization;
    const role = authorization?.replace('Bearer token-', '').toUpperCase() as Role;
    const ok = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
    if (path === '/auth/login') return body.password === 'incorrect' ? ok({ detail: 'Identifiants invalides.' }, 401) : ok({ access_token: 'token-' + body.username.replace('demo-', ''), expires_at: new Date(Date.now() + 3600000).toISOString() });
    if (path === '/auth/me') return ok(userFor(role));
    if (path === '/auth/logout') return ok(null, 204);
    if (path === '/auth/citizen/request-otp') return otpDisabled ? ok({ detail: 'La simulation OTP locale n’est pas activée.' }, 503) : ok({ challenge_id: 'challenge-1', message: 'Code envoyé au simulateur local.' }, 202);
    if (path === '/auth/citizen/verify-otp') return ok({ access_token: 'token-citizen', expires_at: new Date(Date.now() + 3600000).toISOString() });
    if (path === '/citizen/polling-station') return ok(station);
    if (path === '/polling-stations') return ok(page([station]));
    if (path === '/elections') return ok(page([election]));
    if (path === '/candidates') return ok(page([candidate]));
    if (path === '/assignments') return ok(page([{ election_id: election.id, polling_station_id: station.id, user_id: 'agent' }]));
    if (path === `/elections/${election.id}/polling-stations`) return ok(page([{ election_id: election.id, polling_station_id: station.id, registered_voters: 100 }]));
    if (path === `/elections/${election.id}/candidates`) return ok(page([{ candidate_id: candidate.id }]));
    const report = { id: 'report-1', election_id: election.id, polling_station_id: station.id, created_by: 'agent', current_revision: 1, created_at: baseRevision.created_at };
    if (path === '/reports' && method === 'POST') { reportExists = true; return ok(revision, 201); }
    if (path === '/reports') { if (failReports) { const status = failReports; failReports = 0; return ok({ detail: status === 401 ? 'Session expirée.' : 'Base de données indisponible.' }, status); } return ok(page(reportExists ? [report] : [])); }
    if (path === '/reports/report-1') return ok(report);
    if (path === '/reports/report-1/history') return ok(page([{ id: 'event-1', revision_id: revision.id, action: revision.status === 'DRAFT' ? 'CREATED' : revision.status, created_at: revision.created_at, note: '' }]));
    if (path === '/reports/report-1/validations') return ok(page([]));
    if (path === '/reports/report-1/revisions') return ok(page([revision]));
    if (path === '/reports/report-1/revisions/1') return ok(revision);
    if (path === '/reports/report-1/revisions/1/documents' && method === 'GET') return ok(documents);
    if (path === '/reports/report-1/revisions/1/documents' && method === 'POST') {
      const file = (body as FormData).get('file') as File;
      const document: ReportDocument = { id: 'document-1', revision_id: revision.id, uploaded_by: 'agent', original_filename: file.name, media_type: file.type, size_bytes: file.size, sha256: 'a'.repeat(64), storage_provider: 'LOCAL', processing_status: 'STORED', created_at: revision.created_at, processed_at: null, failure_reason: null };
      documents = [document]; return ok(document, 201);
    }
    if (path === '/reports/report-1/revisions/1/documents/document-1' && method === 'DELETE') { documents = []; return ok(null, 204); }
    if (path === '/reports/report-1/revisions/1/incidents' && method === 'GET') return ok(incidents);
    if (path === '/reports/report-1/revisions/1/incidents' && method === 'POST') {
      const incident: Incident = { id: 'incident-1', revision_id: revision.id, created_by: 'agent', category: body.category, description: body.description, created_at: revision.created_at, attachments: [] };
      incidents = [incident]; return ok(incident, 201);
    }
    if (path === '/reports/report-1/revisions/1/incidents/incident-1/attachments' && method === 'POST') {
      const file = (body as FormData).get('file') as File;
      const photo = { id: 'photo-1', incident_id: 'incident-1', uploaded_by: 'agent', original_filename: file.name, media_type: file.type as 'image/jpeg', size_bytes: file.size, sha256: 'b'.repeat(64), storage_provider: 'LOCAL' as const, created_at: revision.created_at };
      incidents = [{ ...incidents[0], attachments: [photo] }]; return ok(photo, 201);
    }
    if (path === '/reports/report-1/revisions/1/incidents/incident-1/attachments/photo-1' && method === 'DELETE') { incidents = [{ ...incidents[0], attachments: [] }]; return ok(null, 204); }
    if (path.startsWith('/reports/report-1/revisions/1/')) {
      if (forceConflict) return ok({ detail: 'Version obsolète : rechargez le PV.' }, 409);
      if (path.endsWith('/results')) revision = { ...revision, ...body, edit_version: revision.edit_version + 1 };
      if (path.endsWith('/submit')) revision = { ...revision, status: 'SUBMITTED', edit_version: revision.edit_version + 1 };
      if (path.endsWith('/review')) revision = { ...revision, status: 'PENDING_VALIDATION', edit_version: revision.edit_version + 1 };
      if (path.endsWith('/decision')) revision = { ...revision, status: body.decision, edit_version: revision.edit_version + 1 };
      return ok(revision);
    }
    if (path === '/accounts') return method === 'POST' ? ok(body, 201) : ok(page([{ ...userFor('ADMIN'), username: 'demo-admin', active: true }]));
    throw new Error(`Unexpected test request: ${method} ${path}`);
  }));
});
function app(path = '/connexion') { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>); }
async function login(role = 'agent') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Identifiant'), `demo-${role}`);
  await user.type(screen.getByLabelText('Mot de passe', { exact: true }), 'fixture-password-only');
  await user.click(screen.getByRole('button', { name: /^Se connecter$/ }));
  return user;
}
test('une route privée redirige vers la connexion et une erreur ne crée pas de session', async () => {
  app('/app/pv'); const user = userEvent.setup();
  await user.type(screen.getByLabelText('Identifiant'), 'demo-agent'); await user.type(screen.getByLabelText('Mot de passe', { exact: true }), 'incorrect');
  await user.click(screen.getByRole('button', { name: /^Se connecter$/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Identifiants invalides');
  expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
});
test('navigation agent, données de l’API et jeton conservé uniquement en mémoire', async () => {
  app(); const user = await login();
  expect(await screen.findByRole('heading', { name: 'Vue d’ensemble' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Utilisateurs' })).not.toBeInTheDocument();
  expect(window.localStorage.length).toBe(0); expect(window.sessionStorage.length).toBe(0);
  await user.click(screen.getByRole('link', { name: /^Procès-verbaux$/ }));
  expect(await screen.findByRole('heading', { name: 'Procès-verbaux' })).toBeInTheDocument();
  await user.type(screen.getByRole('searchbox'), 'inexistant');
  expect(screen.getByText('Aucun procès-verbal à afficher')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Se déconnecter' }));
  expect(await screen.findByRole('heading', { name: 'Accéder à mon espace' })).toBeInTheDocument();
});
test('un agent ne peut ouvrir une URL administrateur', async () => {
  app('/app/comptes'); await login();
  expect(await screen.findByRole('alert')).toHaveTextContent('Votre rôle ne permet pas');
  expect(calls.some(c => c.path === '/accounts')).toBe(false);
});
test('création d’un PV dans un bureau affecté', async () => {
  reportExists = false; app('/app/pv/nouveau'); const user = await login();
  await screen.findByRole('heading', { name: 'Créer un procès-verbal' });
  await waitFor(() => expect(screen.getByLabelText('Bureau affecté')).toBeEnabled());
  await user.selectOptions(screen.getByLabelText('Bureau affecté'), station.id);
  await user.click(screen.getByRole('button', { name: 'Créer le brouillon' }));
  expect(await screen.findByRole('heading', { name: station.name })).toBeInTheDocument();
  expect(calls.find(c => c.path === '/reports' && c.method === 'POST')?.body).toEqual({ election_id: election.id, polling_station_id: station.id });
});
async function fillResults(user: ReturnType<typeof userEvent.setup>, ballots = '100') {
  for (const [label, value] of [['Bulletins déposés', ballots], ['Suffrages exprimés', '90'], ['Bulletins blancs', '6'], ['Bulletins nuls', '4'], ['Voix — Liste Aurore', '90']]) {
    await user.clear(screen.getByLabelText(label)); await user.type(screen.getByLabelText(label), value);
  }
}
test('saisie cohérente, sauvegarde puis soumission avec la version du serveur', async () => {
  app('/app/pv/report-1'); const user = await login(); await screen.findByLabelText('Bulletins déposés');
  await fillResults(user, '101'); await user.click(screen.getByRole('button', { name: 'Enregistrer les résultats' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('ne peuvent pas dépasser');
  expect(calls.some(c => c.method === 'PUT')).toBe(false);
  await user.clear(screen.getByLabelText('Bulletins déposés')); await user.type(screen.getByLabelText('Bulletins déposés'), '100');
  await user.click(screen.getByRole('button', { name: 'Enregistrer les résultats' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Soumettre le PV' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Soumettre le PV' }));
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmer' }));
  await waitFor(() => expect(revision.status).toBe('SUBMITTED'));
  expect(calls.find(c => c.path.endsWith('/results') && c.method === 'PUT')?.body.expected_version).toBe(1);
  expect(calls.find(c => c.path.endsWith('/submit'))?.body.expected_version).toBe(2);
});
test('le client API transmet les pièces en multipart sans forcer le Content-Type', async () => {
  let request: RequestInit | undefined;
  vi.stubGlobal('fetch', vi.fn(async (_url: string, options: RequestInit) => { request = options; return new Response(JSON.stringify({ id: 'document-1' }), { status: 201, headers: { 'Content-Type': 'application/json' } }); }));
  const data = new FormData(); data.append('expected_version', '1'); data.append('file', new Blob(['%PDF-1.4 synthetic'], { type: 'application/pdf' }), 'pv-fictif.pdf');
  await createApi('token-agent').request('/reports/report-1/revisions/1/documents', { method: 'POST', body: data });
  expect(request?.body).toBe(data);
  expect(request?.headers).toMatchObject({ Accept: 'application/json', Authorization: 'Bearer token-agent' });
  expect(request?.headers).not.toHaveProperty('Content-Type');
});
test('un agent déclare un incident fictif et ajoute une photographie privée', async () => {
  app('/app/pv/report-1'); const user = await login();
  await screen.findByRole('heading', { name: 'Incidents constatés' });
  await user.selectOptions(screen.getByLabelText('Catégorie d’incident'), 'MATERIAL');
  await user.type(screen.getByLabelText('Description de l’incident'), 'Urne fictive endommagée pendant la préparation.');
  await user.click(screen.getByRole('button', { name: 'Déclarer l’incident' }));
  expect(await screen.findByText('Urne fictive endommagée pendant la préparation.')).toBeInTheDocument();

  const photo = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], 'incident.jpg', { type: 'image/jpeg' });
  await user.upload(screen.getByLabelText('Photographie — Matériel'), photo);
  const photoInput = screen.getByLabelText('Photographie — Matériel');
  fireEvent.submit(photoInput.closest('form')!);
  await waitFor(() => expect(calls.some(c => c.path.endsWith('/incidents/incident-1/attachments') && c.method === 'POST')).toBe(true));
  const upload = calls.find(c => c.path.endsWith('/incidents/incident-1/attachments') && c.method === 'POST');
  expect(upload?.body).toBeInstanceOf(FormData);
  expect(await screen.findByText('incident.jpg')).toBeInTheDocument();
});
test('un conflit conserve les valeurs saisies et indique de recharger', async () => {
  forceConflict = true; app('/app/pv/report-1'); const user = await login(); await screen.findByLabelText('Bulletins déposés');
  await fillResults(user); await user.click(screen.getByRole('button', { name: 'Enregistrer les résultats' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Version obsolète');
  expect(screen.getByLabelText('Bulletins déposés')).toHaveValue(100);
});
test('validation humaine : démarrer la revue et rejeter avec un motif', async () => {
  revision = { ...revision, status: 'SUBMITTED', ballots_cast: 100, valid_votes: 90, blank_votes: 6, invalid_votes: 4, results: [{ candidate_id: candidate.id, votes: 90 }] };
  app('/app/pv/report-1'); const user = await login('validator');
  await user.click(await screen.findByRole('button', { name: 'Commencer la vérification' }));
  await user.click(await screen.findByRole('button', { name: 'Rejeter le PV' }));
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmer' }));
  expect(calls.some(c => c.path.endsWith('/decision'))).toBe(false);
  await user.type(screen.getByLabelText('Motif obligatoire'), 'Totaux à vérifier.');
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmer' }));
  await waitFor(() => expect(revision.status).toBe('REJECTED'));
  expect(calls.find(c => c.path.endsWith('/decision'))?.body).toEqual({ expected_version: 2, decision: 'REJECTED', reason: 'Totaux à vérifier.' });
});
test('un administrateur crée un compte sans pouvoir approuver les PV', async () => {
  app('/app/comptes'); const user = await login('admin');
  await user.click(await screen.findByRole('button', { name: 'Créer un compte' }));
  await user.type(screen.getByLabelText('Nom affiché'), 'Agent fictif 02'); await user.type(screen.getByLabelText('Code utilisateur'), 'DEMO-AGENT-02');
  await user.type(screen.getByLabelText('Identifiant de connexion'), 'demo-agent-02'); await user.type(screen.getByLabelText(/Mot de passe initial/), 'fixture-password-only');
  await user.selectOptions(screen.getByLabelText('Rôle'), 'AGENT'); await user.click(screen.getByRole('button', { name: 'Enregistrer le compte' }));
  await waitFor(() => expect(calls.find(c => c.path === '/accounts' && c.method === 'POST')?.body.role).toBe('AGENT'));
  expect(screen.queryByRole('button', { name: 'Approuver le PV' })).not.toBeInTheDocument();
});
test('OTP indisponible : erreur affichée sans faux succès', async () => {
  otpDisabled = true; app(); const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: /^Citoyen$/ }));
  await user.type(await screen.findByLabelText(/Référence citoyenne fictive/), 'DEMO-CIN-0001'); await user.click(screen.getByRole('button', { name: 'Recevoir un code' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('n’est pas activée'); expect(screen.queryByLabelText('Code de vérification')).not.toBeInTheDocument();
});
test('OTP citoyen : vérification puis consultation du seul bureau personnel', async () => {
  app(); const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: /^Citoyen$/ }));
  await user.type(await screen.findByLabelText(/Référence citoyenne fictive/), 'DEMO-CIN-0001'); await user.click(screen.getByRole('button', { name: 'Recevoir un code' }));
  await user.type(await screen.findByLabelText(/Code de vérification/), '123456'); await user.click(screen.getByRole('button', { name: 'Vérifier le code' }));
  expect(await screen.findByText('Votre bureau')).toBeInTheDocument(); expect(screen.queryByRole('link', { name: 'Procès-verbaux' })).not.toBeInTheDocument();
});
test('un échec de chargement propose une nouvelle tentative', async () => {
  failReports = 503; app(); const user = await login(); expect(await screen.findByRole('alert')).toHaveTextContent('indisponible');
  await user.click(screen.getByRole('button', { name: 'Réessayer' })); expect(await screen.findByRole('heading', { name: 'Vue d’ensemble' })).toBeInTheDocument();
});
test('une réponse 401 efface la session et revient à la connexion', async () => {
  app(); const user = await login(); await screen.findByRole('heading', { name: 'Vue d’ensemble' }); failReports = 401;
  await user.click(screen.getByRole('button', { name: /^Actualiser$/ }));
  expect(await screen.findByRole('heading', { name: 'Accéder à mon espace' })).toBeInTheDocument(); expect(screen.getByRole('status')).toHaveTextContent('expiré');
});
test('la lecture paginée ne perd pas les éléments après la première page', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('offset=0') ? { items: ['a'], total: 2 } : { items: ['b'], total: 2 }), { status: 200 })));
  expect(await createApi().all('/example')).toEqual(['a', 'b']);
});
test.each([[-1, 100, true], [1.5, 100, true], [101, 100, true], [100, 100, true]])('contrôles des totaux invalides : %s', (ballots, registered, enforce) => {
  expect(validateCounts({ ballots_cast: ballots, valid_votes: 90, blank_votes: 0, invalid_votes: 0, results: [{ candidate_id: 'x', votes: 90 }] }, registered, enforce)).not.toBeNull();
});
test('respect de la règle de cohérence configurable', () => {
  expect(validateCounts({ ballots_cast: 100, valid_votes: 90, blank_votes: 0, invalid_votes: 0, results: [{ candidate_id: 'x', votes: 90 }] }, 100, false)).toBeNull();
});
