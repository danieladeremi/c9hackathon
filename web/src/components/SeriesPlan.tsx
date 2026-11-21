import { useEffect, useMemo, useState } from 'react'
import { api, type Champion, type PlannedPick, type SeriesIn, type WhatIf } from '../api'
import { GAMES_IN } from '../series'

interface Props {
  series: SeriesIn
  c9Id: string
  opponentId: string
  teamNames: Map<string, string>
  champions: Champion[]
  plan: PlannedPick[]
  onPlanChange: (plan: PlannedPick[]) => void
}

const STATUS_LABEL = { open: 'open', at_risk: 'at risk', planned: 'planned', gone: 'gone' } as const

/** "If we take X in game N, what is left for games 3-5?" for both rosters. */
export function SeriesPlan({ series, c9Id, opponentId, teamNames, champions, plan, onPlanChange }: Props) {
  const maxGames = GAMES_IN[series.format]
  const [result, setResult] = useState<WhatIf | null>(null)
  const [error, setError] = useState<string | null>(null)
  const current = result?.current_game ?? 1
  const [atGame, setAtGame] = useState(1)
  const [draftGame, setDraftGame] = useState<number | null>(null)
  const [draftTeam, setDraftTeam] = useState(c9Id)
  const [draftName, setDraftName] = useState('')
  const byName = useMemo(() => new Map(champions.map((c) => [c.name.toLowerCase(), c])), [champions])
  const names = useMemo(() => new Map(champions.map((c) => [c.champion_id, c.name])), [champions])
  const short = (id: string) => (id === c9Id ? 'C9' : teamNames.get(id) ?? 'Opponent')

  const target = Math.max(atGame, current)
  useEffect(() => {
    let live = true
    api
      .whatIf(series, plan, target)
      .then((r) => live && (setResult(r), setError(null)))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [series, plan, target])

  const add = () => {
    const champ = byName.get(draftName.trim().toLowerCase())
    if (!champ) {
      setError(`No champion called "${draftName}"`)
      return
    }
    onPlanChange([...plan, { game_number: draftGame ?? current, team_id: draftTeam, champion_id: champ.champion_id }])
    setDraftName('')
  }

  const games = Array.from({ length: maxGames - current + 1 }, (_, i) => current + i)
  return (
    <div className="pad">
      <h3 className="insight-title">Plan picks across the series</h3>
      <p className="evidence">
        Add the picks you expect ("C9 takes Rell in game 1"), then see what each player has left at the start of a later game.
        Fearless locks every pick for both teams.
      </p>
      <div className="plan-form">
        <select value={draftGame ?? current} onChange={(e) => setDraftGame(Number(e.target.value))} aria-label="Game">
          {games.map((g) => (
            <option key={g} value={g}>Game {g}</option>
          ))}
        </select>
        <div className="seg">
          <button className={draftTeam === c9Id ? 'seg-on' : ''} onClick={() => setDraftTeam(c9Id)}>C9</button>
          <button className={draftTeam === opponentId ? 'seg-on' : ''} onClick={() => setDraftTeam(opponentId)}>{short(opponentId)}</button>
        </div>
        <input
          list="plan-champions"
          placeholder="Champion"
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          aria-label="Champion to plan"
        />
        <datalist id="plan-champions">
          {champions.map((c) => (
            <option key={c.champion_id} value={c.name} />
          ))}
        </datalist>
        <button className="primary" onClick={add} disabled={!draftName.trim()}>Add</button>
      </div>
      {plan.length > 0 && (
        <ul className="plan-list">
          {plan.map((p, i) => (
            <li key={`${p.champion_id}-${i}`} className={p.team_id === c9Id ? 'plan-chip plan-c9' : 'plan-chip'}>
              G{p.game_number} · {short(p.team_id)} · {names.get(p.champion_id) ?? p.champion_id}
              <button className="ghost x" aria-label="Remove" onClick={() => onPlanChange(plan.filter((_, j) => j !== i))}>×</button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="evidence warn">{error}</p>}

      <div className="plan-at">
        <span className="muted">Pools at the start of</span>
        <div className="seg">
          {games.map((g) => (
            <button key={g} className={target === g ? 'seg-on' : ''} onClick={() => setAtGame(g)}>G{g}</button>
          ))}
        </div>
      </div>
      {result && (
        <p className="evidence">
          {result.at_game > result.current_game
            ? `Game ${result.at_game} is played ${Math.round(result.p_at_game_played * 100)}% of the time from here (coin-flip games). `
            : ''}
          "At risk" = the other team takes it first at least {Math.round(result.thresholds.at_risk * 100)}% of the time over the
          {' '}{result.expected_games_before.toFixed(1)} games before then. Depth = share of a player's pro games on champions still open.
        </p>
      )}

      {result?.teams.map((team) => (
        <div key={team.team_id} className="pool-team">
          <h3 className="insight-title">{teamNames.get(team.team_id) ?? team.team_id}</h3>
          {team.players.map((p) => {
            const changed = p.depth_with_plan < p.depth_without_plan - 0.005
            return (
              <div key={p.player_id} className="pool-row">
                <div className="pool-player">
                  <strong>{p.name}</strong>
                  <span className="muted">{p.role}</span>
                  <span className={p.thin ? 'pool-left pool-low' : 'pool-left'} title={`Expected depth after at-risk picks: ${Math.round(p.expected_depth * 100)}%`}>
                    {Math.round(p.depth_with_plan * 100)}% open
                    {changed ? ` (was ${Math.round(p.depth_without_plan * 100)}%)` : ''}
                    {p.thin ? ' · thin' : ''}
                  </span>
                </div>
                <span className="depth" aria-hidden="true">
                  <span className="depth-was" style={{ width: `${Math.round(p.depth_without_plan * 100)}%` }} />
                  <span className="depth-now" style={{ width: `${Math.round(p.depth_with_plan * 100)}%` }} />
                </span>
                <ul className="pool-champs">
                  {p.champions.map((c) => (
                    <li
                      key={c.champion_id}
                      className={`pchip st-${c.status}`}
                      title={
                        c.status === 'gone' || c.status === 'planned'
                          ? `${STATUS_LABEL[c.status]}: game ${c.detail?.game} by ${short(c.detail?.team_id ?? '')}`
                          : c.status === 'at_risk'
                            ? `${Math.round(c.risk * 100)}% chance the other team takes it first`
                            : `${c.games} pro games`
                      }
                    >
                      {c.name}
                      {c.status === 'at_risk' && <span className="risk"> {Math.round(c.risk * 100)}%</span>}
                      {(c.status === 'gone' || c.status === 'planned') && <span className="muted"> G{c.detail?.game}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
