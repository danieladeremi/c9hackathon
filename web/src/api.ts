// Types and fetchers for the FastAPI backend (planner/api.py).

export const C9_TEAM_ID = '47351'

export type Role = 'top' | 'jungle' | 'mid' | 'bot' | 'support'
export const ROLES: Role[] = ['top', 'jungle', 'mid', 'bot', 'support']

export interface Team {
  team_id: string
  name: string
  games: number
  last_game: string
  last_event: string
}

export interface Champion {
  champion_id: string
  name: string
  games: number
  win_rate: number
  main_role: Role | 'unknown'
}

export interface OrderSlot {
  seq: number
  action: 'ban' | 'pick'
  who: 'first' | 'second'
  phase: 'ban1' | 'pick1' | 'ban2' | 'pick2'
}

export interface GameIn {
  blue_team: string
  red_team: string
  first_pick_team: string
  actions: (string | null)[]
  winner: string | null
}

export interface SeriesIn {
  team_a: string
  team_b: string
  format: 'bo1' | 'bo3' | 'bo5'
  games: GameIn[]
  since?: string | null
}

export interface Candidate {
  champion_id: string
  name: string
  count: number
  same_game_number: number
  probability: number
}

export interface NextSlot {
  seq: number
  action: 'ban' | 'pick'
  team_id: string
  phase: OrderSlot['phase']
  prediction: { games: number; candidates: Candidate[] }
}

export interface PoolChampion {
  champion_id: string
  name: string
  games: number
  wins: number
  last_played: string
  available: boolean
}

export interface PlayerPool {
  player_id: string
  name: string
  role: Role
  champions: PoolChampion[]
}

export interface DraftState {
  games: {
    index: number
    next: NextSlot | null
    unavailable: Record<string, string>
    fearless_locked: Record<string, { game: number; team_id: string }>
  }[]
  current_game: number | null
  wins: Record<string, number>
  decided: boolean
  pools: Record<string, PlayerPool[]>
}

export interface TendencyRow {
  champion_id: string
  name: string
  count: number
  rate: number
  wins?: number
  role?: Role
  player?: string
  phase1: number
  phase2: number
}

export interface Tendencies {
  team_id: string
  game_number: number | null
  games: number
  bans: TendencyRow[]
  picks: TendencyRow[]
  bans_against: TendencyRow[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(`${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  teams: () => request<Team[]>('/api/teams'),
  champions: () => request<Champion[]>('/api/champions'),
  order: () => request<OrderSlot[]>('/api/draft/order'),
  tendencies: (teamId: string, gameNumber?: number, since?: string | null) => {
    const params = new URLSearchParams()
    if (gameNumber) params.set('game_number', String(gameNumber))
    if (since) params.set('since', since)
    return request<Tendencies>(`/api/teams/${teamId}/tendencies?${params}`)
  },
  draftState: (series: SeriesIn) =>
    request<DraftState>('/api/draft/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(series),
    }),
}
