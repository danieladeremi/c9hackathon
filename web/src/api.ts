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

export type DraftAction = 'ban' | 'pick'
export type DraftPhase = 'ban1' | 'pick1' | 'ban2' | 'pick2'

export interface HitRate {
  hits: number
  slots: number
  rate: number | null
  sufficient_sample: boolean
}

export interface PredictorScope {
  slots: number
  skipped_insufficient_history: number
  skipped_null_action: number
  team: Record<'top_1' | 'top_3' | 'top_5', HitRate>
  league_popularity: Record<'top_1' | 'top_3' | 'top_5', HitRate>
}

export interface PredictorAccuracy {
  cutoff: string
  holdout_games: number
  evaluated_slots: number
  minimum_history_games: number
  minimum_evaluation_slots: number
  by_action: Record<DraftAction, PredictorScope>
  by_phase: Record<DraftPhase, PredictorScope>
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
  action: DraftAction
  team_id: string
  phase: DraftPhase
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

export type Evidence = 'strong' | 'some' | 'weak'

export interface MetricEstimate {
  estimate: number | null
  raw: number | null
  low: number | null
  high: number | null
  evidence: Evidence | null
}

export interface WpaCandidate {
  champion_id: string
  name: string
  role: Role
  games: number
  win_rate_raw: number | null
  w0_mean: number | null
  lane_gold14: MetricEstimate
  early: MetricEstimate
  total: MetricEstimate
  vs: { games: number; lane_gold14: MetricEstimate; early: MetricEstimate } | null
}

export interface WpaCandidates {
  role: Role
  opp_champion_id: string | null
  opp_name: string | null
  candidates: WpaCandidate[]
}

export interface SeriesValueRow {
  champion_id: string
  name: string
  denial: number
  cost: number
  net: number
  their_picks: number
  our_picks: number
  their_player: string | null
  their_player_games: number
  our_player: string | null
  our_player_games: number
  playable: boolean
}

export interface SeriesValue {
  us: string
  them: string
  game_number: number
  future_game_probabilities: number[]
  expected_future_games: number
  history_games: { us: number; them: number; window: number }
  playable_min_games: number
  champions: SeriesValueRow[]
  note: string
  accuracy: { log_loss: number; constant_log_loss: number; ece: number; rows: number } | null
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
  predictorAccuracy: () => request<PredictorAccuracy>('/api/predictor/accuracy'),
  tendencies: (teamId: string, gameNumber?: number, since?: string | null) => {
    const params = new URLSearchParams()
    if (gameNumber) params.set('game_number', String(gameNumber))
    if (since) params.set('since', since)
    return request<Tendencies>(`/api/teams/${teamId}/tendencies?${params}`)
  },
  seriesValue: (series: SeriesIn, top = 12) =>
    request<SeriesValue>(`/api/draft/series-value?top=${top}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(series),
    }),
  wpaCandidates: (role: Role, oppChampionId: string | null, exclude: string[], limit = 8) => {
    const params = new URLSearchParams({ role, limit: String(limit) })
    if (oppChampionId) params.set('opp_champion_id', oppChampionId)
    for (const id of exclude) params.append('exclude', id)
    return request<WpaCandidates>(`/api/wpa/candidates?${params}`)
  },
  draftState: (series: SeriesIn) =>
    request<DraftState>('/api/draft/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(series),
    }),
}
