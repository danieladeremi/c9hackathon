import { useEffect, useMemo, useState } from 'react'
import {
  api,
  ROLES,
  type Champion,
  type Evidence,
  type MetricEstimate,
  type OrderSlot,
  type Role,
  type SeriesIn,
  type SeriesValue,
  type WpaCandidates,
} from '../api'

interface Props {
  series: SeriesIn
  gameIndex: number
  c9Id: string
  oppName: string
  champions: Champion[]
  order: OrderSlot[]
  unavailable: Record<string, string>
  onSelect: (championId: string) => void
}

const ROLE_LABEL: Record<Role, string> = { top: 'Top', jungle: 'Jungle', mid: 'Mid', bot: 'Bot', support: 'Support' }

function signed(x: number | null, digits = 0) {
  if (x === null) return 'n/a'
  const v = digits ? x.toFixed(digits) : Math.round(x).toString()
  return x > 0 ? `+${v}` : v
}

function EvidenceTag({ evidence }: { evidence: Evidence | null }) {
  if (!evidence) return null
  return <span className={`ev ev-${evidence}`} title={`${evidence} evidence`}>{evidence}</span>
}

/** For a C9 pick: lane options for the chosen role (head-to-head once the enemy laner is known),
 *  and the Fearless series value of taking each champion now. */
export function C9PickPanel({ series, gameIndex, c9Id, oppName, champions, order, unavailable, onSelect }: Props) {
  const game = series.games[gameIndex]
  const mainRole = useMemo(() => new Map(champions.map((c) => [c.champion_id, c.main_role])), [champions])
  const names = useMemo(() => new Map(champions.map((c) => [c.champion_id, c.name])), [champions])

  // Who picked what so far in this game, from the draft order.
  const picks = useMemo(() => {
    const other = game.first_pick_team === game.blue_team ? game.red_team : game.blue_team
    const out: Record<string, string[]> = { [game.blue_team]: [], [game.red_team]: [] }
    order.forEach((slot, i) => {
      const champ = game.actions[i]
      if (slot.action === 'pick' && champ) out[slot.who === 'first' ? game.first_pick_team : other].push(champ)
    })
    return out
  }, [game, order])
  const oppId = series.team_a === c9Id ? series.team_b : series.team_a

  const filled = new Set((picks[c9Id] ?? []).map((c) => mainRole.get(c)))
  const suggestedRole = ROLES.find((r) => !filled.has(r)) ?? 'top'
  const [roleChoice, setRoleChoice] = useState<Role | null>(null)
  const role = roleChoice ?? suggestedRole
  const enemyLaner = (picks[oppId] ?? []).find((c) => mainRole.get(c) === role) ?? null

  const [lane, setLane] = useState<WpaCandidates | null>(null)
  const [value, setValue] = useState<SeriesValue | null>(null)
  const [error, setError] = useState<string | null>(null)
  const excludeKey = Object.keys(unavailable).sort().join(',')

  useEffect(() => {
    let live = true
    api
      .wpaCandidates(role, enemyLaner, excludeKey ? excludeKey.split(',') : [])
      .then((r) => live && setLane(r))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [role, enemyLaner, excludeKey])

  useEffect(() => {
    let live = true
    api
      .seriesValue(series)
      .then((r) => live && setValue(r))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [series])

  return (
    <div className="pad">
      <div className="role-filter" role="group" aria-label="Role C9 is picking for">
        {ROLES.map((r) => (
          <button key={r} className={role === r ? 'chip chip-on' : 'chip'} onClick={() => setRoleChoice(r)}>
            {ROLE_LABEL[r]}
            {filled.has(r) ? ' ✓' : ''}
          </button>
        ))}
      </div>
      {error && <p className="evidence">Could not load: {error}</p>}

      <h3 className="insight-title">
        {ROLE_LABEL[role]} lane options{enemyLaner ? ` vs ${names.get(enemyLaner) ?? 'their pick'}` : ''}
      </h3>
      <p className="evidence">
        Gold lead at 14 minutes{enemyLaner ? ' (head-to-head where there is enough evidence)' : ''}, shrunk for sample size.
        Champions with 10+ pro games in the role. Labels show how much the number can be trusted.
      </p>
      {lane && lane.candidates.length === 0 && <p className="muted">No candidates with enough games.</p>}
      <ol className="rank">
        {lane?.candidates.map((c) => {
          const m: MetricEstimate = c.vs && c.vs.lane_gold14.evidence !== 'weak' ? c.vs.lane_gold14 : c.lane_gold14
          return (
            <li key={c.champion_id}>
              <button
                className="rank-row rank-row-lane"
                onClick={() => onSelect(c.champion_id)}
                title={`Overall: ${signed(c.lane_gold14.estimate)} gold @14 over ${c.games} games. Early-game win probability added: ${signed(
                  c.early.estimate !== null ? c.early.estimate * 100 : null,
                  1,
                )} pts (${c.early.evidence}). Picked by teams with ${c.w0_mean !== null ? Math.round(c.w0_mean * 100) : '?'}% pre-game win chance on average.`}
              >
                <span className="rank-name">{c.name}</span>
                <span className="rank-num">{signed(m.estimate)}</span>
                <EvidenceTag evidence={m.evidence} />
                <span className="rank-n">{c.vs && m === c.vs.lane_gold14 ? `${c.vs.games} h2h` : `${c.games} g`}</span>
              </button>
            </li>
          )
        })}
      </ol>

      <h3 className="insight-title">Fearless: take it now, deny it later</h3>
      {value && (
        <>
          <p className="evidence">
            {value.expected_future_games > 0
              ? `About ${value.expected_future_games.toFixed(1)} games may follow this one. Denies = chance ${oppName} would use it later in the series; costs = chance C9 would want it later.`
              : value.note}
            {value.accuracy &&
              ` Forecast tested on ${value.accuracy.rows.toLocaleString()} 2026 cases: log loss ${value.accuracy.log_loss.toFixed(3)} vs ${value.accuracy.constant_log_loss.toFixed(3)} for a flat guess.`}
          </p>
          {value.expected_future_games > 0 && (
            <ol className="rank">
              {value.champions
                .filter((r) => !unavailable[r.champion_id])
                .slice(0, 8)
                .map((r) => (
                  <li key={r.champion_id}>
                    <button
                      className="rank-row rank-row-fearless"
                      onClick={() => onSelect(r.champion_id)}
                      disabled={!r.playable}
                      title={`${r.their_player ?? oppName}: ${r.their_picks} picks in ${oppName}'s last ${value.history_games.them} games. ${
                        r.our_player ? `${r.our_player} has ${r.our_player_games} pro games on it.` : 'No current C9 player has played it.'
                      }`}
                    >
                      <span className="rank-name">{r.name}</span>
                      <span className="rank-meta">
                        denies {Math.round(r.denial * 100)}% · costs {Math.round(r.cost * 100)}%
                      </span>
                      <span className="rank-num">{signed(r.net * 100)}</span>
                      <span className="rank-n">{r.their_player ? `vs ${r.their_player}` : ''}</span>
                    </button>
                  </li>
                ))}
            </ol>
          )}
        </>
      )}
    </div>
  )
}
