// Pure selection-matching logic for the Kahuna card-first UI: the player
// selects hand cards plus board lines/bridges, and committing must spend
// every selected card. Each selected line/bridge has pay options (the legal
// place/remove variants for it); a selection is committable when some
// assignment of options spends the selected cards exactly.

import type { LegalAction } from '../types'

export interface PayOption {
  action: number
  cost: string[] // 1 card for place, 2 for remove
}

/** Legal place/remove variants, grouped by bridge position. */
export function payOptionsByBridge(legalActions: LegalAction[]): Map<number, PayOption[]> {
  const options = new Map<number, PayOption[]>()
  for (const la of legalActions) {
    if (la.meta.kind === 'place' || la.meta.kind === 'remove') {
      const pos = la.meta.bridge as number
      const opt = { action: la.action, cost: la.meta.spend as string[] }
      options.set(pos, [...(options.get(pos) ?? []), opt])
    }
  }
  return options
}

/**
 * Assign one pay option to every element so that the combined cost fits
 * within `cards` (exact=false) or equals it as a multiset (exact=true).
 * Returns the chosen options in element order, or null if impossible.
 * Tiny inputs (hand <= 5, elements fewer), so backtracking is plenty.
 */
export function matchSelection(
  elements: PayOption[][],
  cards: string[],
  exact: boolean,
): PayOption[] | null {
  const budget = new Map<string, number>()
  for (const c of cards) budget.set(c, (budget.get(c) ?? 0) + 1)
  let spent = 0

  const take = (cost: string[]): boolean => {
    for (let i = 0; i < cost.length; i++) {
      const left = budget.get(cost[i]) ?? 0
      if (left === 0) {
        while (i-- > 0) budget.set(cost[i], (budget.get(cost[i]) ?? 0) + 1)
        return false
      }
      budget.set(cost[i], left - 1)
    }
    spent += cost.length
    return true
  }
  const untake = (cost: string[]) => {
    for (const c of cost) budget.set(c, (budget.get(c) ?? 0) + 1)
    spent -= cost.length
  }

  const solve = (i: number): PayOption[] | null => {
    if (i === elements.length) return !exact || spent === cards.length ? [] : null
    for (const opt of elements[i]) {
      if (!take(opt.cost)) continue
      const rest = solve(i + 1)
      untake(opt.cost)
      if (rest) return [opt, ...rest]
    }
    return null
  }
  return solve(0)
}
