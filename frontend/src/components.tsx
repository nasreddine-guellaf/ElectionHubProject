import { useEffect, useRef, type ReactNode } from 'react';
import { AlertCircle, CheckCircle2, FileText, LoaderCircle, X } from 'lucide-react';
import type { Status } from './types';
import type { useAction } from './hooks';

export const roleLabels = { ADMIN: 'Administrateur', AGENT: 'Agent de bureau', VALIDATOR: 'Validateur', CITIZEN: 'Citoyen' };
export const statusLabels: Record<Status, string> = { DRAFT: 'Brouillon', SUBMITTED: 'Soumis', PROCESSING: 'En traitement', PENDING_VALIDATION: 'En vérification', APPROVED: 'Approuvé', REJECTED: 'À corriger', PUBLISHED: 'Publié', PROCESSING_FAILED: 'Traitement échoué' };
export const number = (value: number) => new Intl.NumberFormat('fr-FR').format(value);
export const date = (value: string) => new Date(value).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
export const dateTime = (value: string) => new Date(value).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });
export function Brand() { return <span className="brand"><img src="/favicon.svg" alt="" /><span>Election<span className="brand-light">Hub</span><small>ESPACE ÉLECTORAL</small></span></span>; }
export function Badge({ status }: { status: Status }) { return <span className={`badge status-${status.toLowerCase()}`}>{statusLabels[status]}</span>; }
export function Loading() { return <div className="loading" role="status"><LoaderCircle className="spin" size={22} /> Chargement des données…</div>; }
export function ErrorBox({ message, retry }: { message?: string; retry?: () => void }) { return message ? <div className="notice error" role="alert"><AlertCircle size={19} /><span>{message}</span>{retry && <button className="text-button" onClick={retry}>Réessayer</button>}</div> : null; }
export function Feedback({ action }: { action: ReturnType<typeof useAction> }) { return <><ErrorBox message={action.error} />{action.success && <div className="notice success" role="status"><CheckCircle2 size={19} />{action.success}</div>}</>; }
export function Empty({ title, children }: { title: string; children?: ReactNode }) { return <div className="empty"><FileText size={30} /><h3>{title}</h3>{children && <p>{children}</p>}</div>; }
export function PageHeading({ eyebrow, title, description, children }: { eyebrow?: string; title: string; description?: string; children?: ReactNode }) { return <div className="page-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="muted">{description}</p>}</div>{children && <div className="heading-actions">{children}</div>}</div>; }
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) { return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>; }
export function Modal({ title, children, close, busy = false }: { title: string; children: ReactNode; close: () => void; busy?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close(); }, []);
  return <dialog ref={dialog} className="modal" aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); if (!busy) close(); }}><div className="modal-heading"><h2 id="modal-title">{title}</h2><button className="icon-button" onClick={close} disabled={busy} aria-label="Fermer"><X size={20} /></button></div>{children}</dialog>;
}
export function Confirm({ title, children, onConfirm, close, action, label = 'Confirmer', danger = false }: { title: string; children: ReactNode; onConfirm: () => Promise<void>; close: () => void; action: ReturnType<typeof useAction>; label?: string; danger?: boolean }) { return <Modal title={title} close={close} busy={action.busy}><p>{children}</p><Feedback action={action} /><div className="form-actions"><button className="button secondary" onClick={close} disabled={action.busy}>Annuler</button><button className={`button ${danger ? 'danger' : ''}`} disabled={action.busy} onClick={() => action.run(onConfirm, '')}>{action.busy ? 'Enregistrement…' : label}</button></div></Modal>; }
