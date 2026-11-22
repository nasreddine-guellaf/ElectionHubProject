import type { Result } from './types';
export interface Counts { ballots_cast: number; valid_votes: number; blank_votes: number; invalid_votes: number; results: Result[] }
export function validateCounts(values: Counts, registered: number, enforceEquation: boolean): string | null {
  if ([values.ballots_cast, values.valid_votes, values.blank_votes, values.invalid_votes, ...values.results.map(r => r.votes)].some(v => !Number.isSafeInteger(v) || v < 0 || v > 2147483647)) return 'Chaque total doit être un entier positif ou nul.';
  if (!values.results.length) return 'Le scrutin doit comporter au moins une liste candidate.';
  if (values.results.reduce((sum, row) => sum + row.votes, 0) !== values.valid_votes) return 'La somme des voix des listes doit être égale aux suffrages exprimés.';
  if (values.ballots_cast > registered) return 'Les bulletins déposés ne peuvent pas dépasser le nombre d’inscrits.';
  if (values.valid_votes > values.ballots_cast || values.blank_votes + values.invalid_votes > values.ballots_cast) return 'Les suffrages exprimés, ou la somme des blancs et nuls, dépassent les bulletins déposés.';
  if (enforceEquation && values.valid_votes + values.blank_votes + values.invalid_votes !== values.ballots_cast) return 'Suffrages exprimés + blancs + nuls doit être égal aux bulletins déposés.';
  return null;
}
