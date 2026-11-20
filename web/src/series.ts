// Client-side series state. The server is the authority on legality (/api/draft/state);
// these helpers only build and edit the plain data sent to it.

import { C9_TEAM_ID, type GameIn, type SeriesIn } from './api'

export const GAMES_IN: Record<SeriesIn['format'], number> = { bo1: 1, bo3: 3, bo5: 5 }

export function newGame(opponent: string, c9Side: 'blue' | 'red', c9FirstPick: boolean): GameIn {
  const blue = c9Side === 'blue' ? C9_TEAM_ID : opponent
  const red = c9Side === 'blue' ? opponent : C9_TEAM_ID
  return { blue_team: blue, red_team: red, first_pick_team: c9FirstPick ? C9_TEAM_ID : opponent, actions: [], winner: null }
}

export function newSeries(opponent: string, format: SeriesIn['format']): SeriesIn {
  return { team_a: C9_TEAM_ID, team_b: opponent, format, games: [newGame(opponent, 'blue', true)] }
}

export function c9Side(game: GameIn): 'blue' | 'red' {
  return game.blue_team === C9_TEAM_ID ? 'blue' : 'red'
}

export function withGame(series: SeriesIn, index: number, change: (g: GameIn) => GameIn): SeriesIn {
  return { ...series, games: series.games.map((g, i) => (i === index ? change(g) : g)) }
}

export function setSetup(game: GameIn, opponent: string, side: 'blue' | 'red', c9FirstPick: boolean): GameIn {
  const fresh = newGame(opponent, side, c9FirstPick)
  return { ...game, blue_team: fresh.blue_team, red_team: fresh.red_team, first_pick_team: fresh.first_pick_team }
}

export function wins(series: SeriesIn): Record<string, number> {
  const out: Record<string, number> = { [series.team_a]: 0, [series.team_b]: 0 }
  for (const g of series.games) if (g.winner) out[g.winner] = (out[g.winner] ?? 0) + 1
  return out
}

export function isDecided(series: SeriesIn): boolean {
  const needed = Math.floor(GAMES_IN[series.format] / 2) + 1
  return Math.max(...Object.values(wins(series))) >= needed
}

/** The next game: by convention the loser of the previous game takes first pick, sides swap. */
export function nextGame(series: SeriesIn): GameIn {
  const prev = series.games[series.games.length - 1]
  const c9Lost = prev.winner !== null && prev.winner !== C9_TEAM_ID
  const side = c9Side(prev) === 'blue' ? 'red' : 'blue'
  return newGame(series.team_b, side, c9Lost)
}

const STORAGE_KEY = 'c9-draft-planner/series'

export function loadSeries(): SeriesIn | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as SeriesIn) : null
  } catch {
    return null
  }
}

export function saveSeries(series: SeriesIn | null): void {
  try {
    if (series) localStorage.setItem(STORAGE_KEY, JSON.stringify(series))
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* storage unavailable: the board still works, it just won't survive a reload */
  }
}
