import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Building2, CheckCircle2, ClipboardCheck, Eye, EyeOff, LockKeyhole, LogOut, ShieldCheck, Users } from 'lucide-react';
import { publicApi } from '../api';
import { Brand, Empty, ErrorBox, Feedback, Field, Loading, PageHeading, number, roleLabels } from '../components';
import { useAction, useLoad } from '../hooks';
import { useSession } from '../session';
import type { Station, Token } from '../types';

export function LoginPage() {
  const { session, notice, establish } = useSession();
  const [mode, setMode] = useState<'staff' | 'citizen'>('staff');
  const [challenge, setChallenge] = useState('');
  const [message, setMessage] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const action = useAction();
  const navigate = useNavigate();
  const location = useLocation();
  if (session) {
    const requested = location.state?.from;
    const destination = session.user.role === 'CITIZEN'
      ? '/citoyen'
      : typeof requested === 'string' && requested.startsWith('/app')
        ? requested
        : '/app';
    return <Navigate to={destination} replace />;
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    action.run(async () => {
      if (mode === 'citizen' && !challenge) {
        const result = await publicApi.request<{ challenge_id: string; message: string }>('/auth/citizen/request-otp', { method: 'POST', body: { cin: String(form.get('cin')).trim().toUpperCase() } });
        setChallenge(result.challenge_id); setMessage(result.message); return;
      }
      const token = await publicApi.request<Token>(mode === 'staff' ? '/auth/login' : '/auth/citizen/verify-otp', { method: 'POST', body: mode === 'staff' ? { username: String(form.get('username')).trim().toLowerCase(), password: form.get('password') } : { challenge_id: challenge, code: form.get('code') } });
      const user = await establish(token);
      const from = location.state?.from;
      navigate(user.role === 'CITIZEN' ? '/citoyen' : typeof from === 'string' && from.startsWith('/app') ? from : '/app', { replace: true });
    }, '');
  }
  return <div className="login-layout"><section className="login-story"><Link to="/" className="brand-link"><Brand /></Link><div className="login-story-content"><span className="story-tag">CONSULTATION & CONSOLIDATION</span><h1>Chaque bureau.<br />Chaque résultat.<br /><em>Une vision claire.</em></h1><p>Un espace commun pour saisir, vérifier et suivre les résultats électoraux de démonstration.</p><div className="story-workflow"><div><span><ClipboardCheck size={21} /></span><strong>Saisir</strong><small>Par les agents affectés</small></div><div><span><ShieldCheck size={21} /></span><strong>Vérifier</strong><small>Par un validateur habilité</small></div><div><span><CheckCircle2 size={21} /></span><strong>Consolider</strong><small>Avec un historique préservé</small></div></div></div><div className="story-footer"><ShieldCheck size={17} /> Projet académique · Données entièrement fictives</div></section>
    <section className="login-panel"><div className="login-top"><span className="demo-pill">Démonstration locale</span><Link to="/bureaux">Consulter les bureaux</Link></div><div className="login-card"><span className="section-icon"><LockKeyhole size={24} /></span><p className="eyebrow">BIENVENUE SUR ELECTIONHUB</p><h2>Accéder à mon espace</h2><p className="muted">Retrouvez les informations et les actions liées à votre rôle.</p>
      <div className="segmented" role="group" aria-label="Type de connexion"><button className={mode === 'staff' ? 'active' : ''} aria-pressed={mode === 'staff'} onClick={() => { setMode('staff'); action.reset(); }}><Users size={17} />Équipe électorale</button><button className={mode === 'citizen' ? 'active' : ''} aria-pressed={mode === 'citizen'} onClick={() => { setMode('citizen'); action.reset(); }}>Citoyen</button></div>
      {notice && <p className="notice info" role="status">{notice}</p>}<Feedback action={action} />
      <form onSubmit={submit} key={`${mode}-${Boolean(challenge)}`} className="form-stack">
        {mode === 'staff' ? <><Field label="Identifiant"><input name="username" placeholder="demo-agent" autoComplete="username" required maxLength={80} autoCapitalize="none" spellCheck={false} /></Field><Field label="Mot de passe"><span className="password-field"><input name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required maxLength={128} /><button type="button" className="icon-button" onClick={() => setShowPassword(v => !v)} aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></span></Field></> : challenge ? <><p className="notice info">{message} Le code reste valable cinq minutes.</p><Field label="Code de vérification" hint="Six chiffres reçus dans le simulateur SMS local."><input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required placeholder="000000" /></Field></> : <Field label="Référence citoyenne fictive" hint="Utilisez uniquement une référence de démonstration."><input name="cin" placeholder="DEMO-CIN-0001" pattern="DEMO-CIN-[A-Z0-9\-]+" required maxLength={50} autoComplete="off" /></Field>}
        <button className="button full" disabled={action.busy}>{action.busy ? 'Veuillez patienter…' : mode === 'staff' ? 'Se connecter' : challenge ? 'Vérifier le code' : 'Recevoir un code'}</button>
        {mode === 'citizen' && challenge && <button type="button" className="text-button" disabled={action.busy} onClick={() => { setChallenge(''); action.reset(); }}>Demander un nouveau code</button>}
      </form><p className="login-help">{mode === 'staff' ? 'Un accès est nécessaire. Contactez votre administrateur pour obtenir vos identifiants.' : 'Le parcours citoyen nécessite l’activation du simulateur local. Aucun SMS réel n’est envoyé.'}</p><div className="login-disclaimer"><ShieldCheck size={17} /><span>Cette plateforme ne permet pas de voter. Aucune donnée électorale réelle n’est utilisée.</span></div>
    </div><div className="login-bottom">ElectionHub · Consultation et consolidation des résultats</div></section></div>;
}

export function PublicStations() {
  const load = useLoad(signal => publicApi.all<Station>('/polling-stations', signal), []);
  const [search, setSearch] = useState('');
  const items = load.data?.filter(s => `${s.name} ${s.code}`.toLowerCase().includes(search.toLowerCase()));
  return <div className="public-page"><header className="public-header"><Link to="/" className="brand-link"><Brand /></Link><Link className="button" to="/connexion">Se connecter</Link></header><main className="public-container"><PageHeading eyebrow="ANNUAIRE PUBLIC" title="Les bureaux de démonstration" description="Un référentiel fictif, accessible à tous. Aucun résultat individuel ni donnée citoyenne n’est publié ici." /><Field label="Rechercher un bureau"><input type="search" placeholder="Nom ou code du bureau" value={search} onChange={e => setSearch(e.target.value)} /></Field><ErrorBox message={load.error} retry={load.reload} />{load.loading && <Loading />}<div className="station-grid">{items?.map(s => <StationCard key={s.id} station={s} />)}</div>{items?.length === 0 && <Empty title="Aucun bureau trouvé">Essayez un autre nom ou code.</Empty>}<p className="muted">La publication des résultats et le tableau de bord public seront disponibles après l’intégration analytique.</p></main></div>;
}
export function StationCard({ station, children }: { station: Station; children?: React.ReactNode }) { return <article className="station-card"><span className="section-icon"><Building2 size={22} /></span><span className="code">{station.code}</span><h3>{station.name}</h3><p><strong>{number(station.registered_voters)}</strong> inscrits fictifs</p>{children}</article>; }
export function CitizenPage() {
  const { session, api, logout } = useSession();
  const action = useAction();
  const load = useLoad(signal => api.request<Station>('/citizen/polling-station', { signal }), [api]);
  return <div className="public-page"><header className="public-header"><Brand /><button className="button secondary" disabled={action.busy} onClick={() => action.run(logout)}><LogOut size={17} />Se déconnecter</button></header><main className="public-container"><PageHeading eyebrow="ESPACE CITOYEN" title={`Bienvenue, ${session!.user.display_name}`} description="Retrouvez le bureau associé à votre référence de démonstration." /><Feedback action={action} /><ErrorBox message={load.error} retry={load.reload} />{load.loading && <Loading />}{load.data && <div className="citizen-grid"><StationCard station={load.data}><span className="badge status-approved">Votre bureau</span></StationCard><section className="panel prose"><ShieldCheck size={26} /><h2>Un espace de consultation</h2><p>Votre accès permet uniquement de consulter votre bureau fictif. Vous ne pouvez pas voter ni enregistrer un choix électoral sur ElectionHub.</p><p>Les résultats publics seront consultables après leur validation et leur publication.</p><Link to="/bureaux" className="text-button">Consulter l’annuaire des bureaux</Link></section></div>}</main></div>;
}
export function ProfilePage() {
  const { api, session, clear } = useSession();
  const action = useAction();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    if (form.get('new_password') !== form.get('confirm_password')) { action.setError('Les nouveaux mots de passe ne correspondent pas.'); return; }
    action.run(async () => { await api.request('/auth/password', { method: 'POST', body: { current_password: form.get('current_password'), new_password: form.get('new_password') } }); clear('Mot de passe modifié. Reconnectez-vous avec votre nouveau mot de passe.'); });
  }
  return <><PageHeading eyebrow="MON COMPTE" title="Profil & sécurité" description={`${session!.user.display_name} · ${roleLabels[session!.user.role]}`} /><section className="panel narrow"><h2>Changer mon mot de passe</h2><p className="muted">Cette modification ferme toutes vos sessions actives.</p><Feedback action={action} /><form onSubmit={submit} className="form-stack"><Field label="Mot de passe actuel"><input name="current_password" type="password" autoComplete="current-password" required maxLength={128} /></Field><Field label="Nouveau mot de passe" hint="12 à 128 caractères."><input name="new_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128} /></Field><Field label="Confirmer le nouveau mot de passe"><input name="confirm_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128} /></Field><button className="button" disabled={action.busy}>Modifier le mot de passe</button></form></section></>;
}
