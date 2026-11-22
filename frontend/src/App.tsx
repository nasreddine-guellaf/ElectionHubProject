import { useEffect, useState } from 'react';
import { Link, Navigate, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { Building2, ClipboardCheck, FileText, LayoutDashboard, LogOut, Menu, ScrollText, Settings2, ShieldCheck, Users, X } from 'lucide-react';
import { Brand, ErrorBox, Loading, roleLabels } from './components';
import { SessionProvider, useSession } from './session';
import { WorkspaceProvider, useWorkspace } from './workspace';
import { useAction } from './hooks';
import { CitizenPage, LoginPage, ProfilePage, PublicStations } from './pages/Auth';
import { Dashboard, ReportsPage } from './pages/Dashboard';
import { NewReport, ReportDetail } from './pages/Reports';
import { AccountsPage, AuditPage, ElectionsPage, StationsPage } from './pages/Admin';
import type { Role } from './types';

function Protected({ roles }: { roles: Role[] }) {
  const { session } = useSession();
  const location = useLocation();
  if (!session) return <Navigate to="/connexion" state={{ from: location.pathname }} replace />;
  if (!roles.includes(session.user.role)) return <div className="public-container"><ErrorBox message="Votre rôle ne permet pas d’accéder à cette page." /><Link className="button" to={session.user.role === 'CITIZEN' ? '/citoyen' : '/app'}>Revenir à mon espace</Link></div>;
  return <Outlet />;
}
function Shell() {
  const { session, logout } = useSession();
  const { data, loading, error, reload, electionId, setElectionId } = useWorkspace();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const action = useAction();
  useEffect(() => { setOpen(false); document.getElementById('main-content')?.focus(); }, [location.pathname]);
  const user = session!.user;
  const links = [
    { to: '/app', label: 'Vue d’ensemble', Icon: LayoutDashboard, end: true },
    { to: '/app/pv', label: user.role === 'VALIDATOR' ? 'Validation des PV' : 'Procès-verbaux', Icon: ClipboardCheck },
    { to: '/app/bureaux', label: user.role === 'AGENT' ? 'Mes bureaux' : 'Bureaux de vote', Icon: Building2 },
    ...(user.role === 'ADMIN' ? [{ to: '/app/scrutins', label: 'Scrutins & affectations', Icon: Settings2 }, { to: '/app/comptes', label: 'Utilisateurs', Icon: Users }, { to: '/app/audit', label: 'Journal d’audit', Icon: ScrollText }] : []),
  ];
  return <div className="app-shell"><a className="skip-link" href="#main-content">Aller au contenu</a>
    {open && <button className="sidebar-scrim" aria-label="Fermer la navigation" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'is-open' : ''}`}><Link to="/app" className="brand-link"><Brand /></Link>
      <div className="workspace-label"><span className="workspace-icon"><ShieldCheck size={18} /></span><div>Espace opérations<small>{roleLabels[user.role]}</small></div><button className="icon-button mobile-only" onClick={() => setOpen(false)} aria-label="Fermer le menu"><X size={18} /></button></div>
      <p className="nav-label">GESTION ÉLECTORALE</p><nav aria-label="Navigation principale">{links.map(({ to, label, Icon, end }) => <NavLink key={to} to={to} end={end}><Icon size={19} />{label}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="demo-note"><ShieldCheck size={22} /><strong>Un cadre de démonstration</strong><p>Données fictives. Aucun vote électronique.</p></div><NavLink to="/app/profil" className="user-card"><span className="avatar">{user.display_name.slice(0, 1)}</span><span><strong>{user.display_name}</strong><small>{roleLabels[user.role]}</small></span></NavLink><button className="logout" disabled={action.busy} onClick={() => action.run(logout)}><LogOut size={17} /> Se déconnecter</button><ErrorBox message={action.error} /></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-only" onClick={() => setOpen(true)} aria-label="Ouvrir le menu"><Menu size={23} /></button><span className="topbar-context">Espace opérations <span>/</span> {links.find(link => link.end ? location.pathname === link.to : location.pathname.startsWith(link.to))?.label || 'Mon profil'}</span></div><div className="topbar-right"><span className="demo-pill">Démonstration</span><span className="avatar small">{user.display_name.slice(0, 1)}</span></div></header>
      <main id="main-content" tabIndex={-1} className="main-content"><div className="scope-bar"><span><span className="scope-dot" /> Données de votre périmètre</span><label className="scope-select"><span className="sr-only">Filtrer le tableau de bord et les PV par scrutin</span><select value={electionId} onChange={event => setElectionId(event.target.value)}><option value="">Tous les scrutins</option>{data?.elections.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label></div>
      <ErrorBox message={error} retry={reload} />{!data ? (loading && <Loading />) : <Outlet />}
      </main><footer className="app-footer"><span>ElectionHub · Plateforme de démonstration</span><span>Les résultats approuvés ne sont pas encore publiés.</span></footer>
    </div>
  </div>;
}
function StaffShell() { const { session } = useSession(); return <WorkspaceProvider key={session!.user.id}><Shell /></WorkspaceProvider>; }
export function App() { return <SessionProvider><Routes>
  <Route path="/" element={<Navigate to="/connexion" replace />} />
  <Route path="/connexion" element={<LoginPage />} /><Route path="/bureaux" element={<PublicStations />} />
  <Route element={<Protected roles={['CITIZEN']} />}><Route path="/citoyen" element={<CitizenPage />} /></Route>
  <Route element={<Protected roles={['ADMIN', 'AGENT', 'VALIDATOR']} />}><Route path="/app" element={<StaffShell />}>
    <Route index element={<Dashboard />} /><Route path="pv" element={<ReportsPage />} />
    <Route element={<Protected roles={['AGENT']} />}><Route path="pv/nouveau" element={<NewReport />} /></Route>
    <Route path="pv/:id" element={<ReportDetail />} /><Route path="bureaux" element={<StationsPage />} /><Route path="profil" element={<ProfilePage />} />
    <Route element={<Protected roles={['ADMIN']} />}><Route path="scrutins" element={<ElectionsPage />} /><Route path="comptes" element={<AccountsPage />} /><Route path="audit" element={<AuditPage />} /></Route>
  </Route></Route>
  <Route path="*" element={<div className="public-container"><FileText size={32} /><h1>Page introuvable</h1><Link className="button" to="/">Revenir à l’accueil</Link></div>} />
  </Routes></SessionProvider>; }
