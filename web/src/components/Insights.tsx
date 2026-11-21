import { useState } from 'react'
import type { NextSlot, PlayerPool, PredictorAccuracy, Tendencies, TendencyRow } from '../api'

interface Props {
  next: NextSlot | null
  c9Id: string
  opponentId: string
  teamNames: Map<string, string>
  gameNumber: number
  unavailable: Record<string, string>
  tendAll: Tendencies | null
  tendGame: Tendencies | null
  pools: Record<string, PlayerPool[]>
  accuracy: PredictorAccuracy | null
  onSelect: (championId: string) => void
}

function pct(x: number) {
  return `${Math.round(x * 100)}%`
}

function Bar({ value }: { value: number }) {
  return (
    <span className="bar" aria-hidden="true">
      <span className="bar-fill" style={{ width: `${Math.min(100, Math.round(value * 100))}%` }} />
    </span>
  )
}

/** Evidence for the current slot, the opponent's habits by game number, and what each roster has left. */
export function Insights(props: Props) {
  const { next, c9Id, opponentId, teamNames, gameNumber, unavailable, tendAll, tendGame, pools, accuracy, onSelect } = props
  const [tab, setTab] = useState<'slot' | 'tendencies' | 'pools'>('slot')
  const opp = teamNames.get(opponentId) ?? 'Opponent'

  return (
    <aside className="insights" aria-label="Insights">
      <div className="tabs" role="tablist">
        {(
          [
            ['slot', 'This slot'],
            ['tendencies', `${opp} habits`],
            ['pools', 'Fearless pools'],
          ] as const
        ).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'tab tab-on' : 'tab'} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'slot' && (
        <SlotView next={next} c9Id={c9Id} opp={opp} unavailable={unavailable} tendGame={tendGame} tendAll={tendAll} pools={pools} accuracy={accuracy} onSelect={onSelect} />
      )}
      {tab === 'tendencies' && <TendencyView opp={opp} gameNumber={gameNumber} tendAll={tendAll} tendGame={tendGame} />}
      {tab === 'pools' && <PoolsView pools={pools} teamNames={teamNames} order={[c9Id, opponentId]} />}
    </aside>
  )
}

function SlotView({ next, c9Id, opp, unavailable, tendGame, tendAll, pools, accuracy, onSelect }: {
  next: NextSlot | null
  c9Id: string
  opp: string
  unavailable: Record<string, string>
  tendGame: Tendencies | null
  tendAll: Tendencies | null
  pools: Record<string, PlayerPool[]>
  accuracy: PredictorAccuracy | null
  onSelect: (id: string) => void
}) {
  if (!next) return <p className="muted pad">Draft complete. Record the winner to plan the next game.</p>
  const c9Acting = next.team_id === c9Id

  if (!c9Acting) {
    const cands = next.prediction.candidates
    return (
      <div className="pad">
        <h3 className="insight-title">Likely {opp} {next.action}s now</h3>
        <p className="evidence">From {next.prediction.games} {opp} drafts in this phase; same game number counts double. Unavailable champions removed.</p>
        <PredictionAccuracy accuracy={accuracy} action={next.action} phase={next.phase} />
        {cands.length === 0 ? (
          <p className="muted">No history for this phase.</p>
        ) : (
          <ol className="rank">
            {cands.map((c) => (
              <li key={c.champion_id}>
                <button className="rank-row" onClick={() => onSelect(c.champion_id)} title={`Record ${c.name} for ${opp}`}>
                  <span className="rank-name">{c.name}</span>
                  <Bar value={c.probability} />
                  <span className="rank-num">{pct(c.probability)}</span>
                  <span className="rank-n">{c.count}×</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    )
  }

  if (next.action === 'ban') {
    const source = tendGame && tendGame.games >= 5 ? tendGame : tendAll
    const threats = (source?.picks ?? []).filter((p) => !unavailable[p.champion_id]).slice(0, 10)
    return (
      <div className="pad">
        <h3 className="insight-title">{opp} picks still open</h3>
        <p className="evidence">
          Their most-picked champions{source === tendGame ? ` in game ${tendGame?.game_number}s` : ''}, from {source?.games ?? 0} games. Ban candidates.
        </p>
        <TendencyList rows={threats} games={source?.games ?? 0} onSelect={onSelect} showPlayer />
      </div>
    )
  }

  const comfort = (pools[c9Id] ?? [])
    .flatMap((p) => p.champions.filter((c) => c.available && !unavailable[c.champion_id]).slice(0, 4).map((c) => ({ ...c, player: p.name, role: p.role })))
    .sort((a, b) => b.games - a.games)
  return (
    <div className="pad">
      <h3 className="insight-title">C9 comfort picks still open</h3>
      <p className="evidence">Each player's most-played champions in pro games that are still legal this game.</p>
      <ol className="rank">
        {comfort.map((c) => (
          <li key={`${c.player}-${c.champion_id}`}>
            <button className="rank-row" onClick={() => onSelect(c.champion_id)}>
              <span className="rank-name">{c.name}</span>
              <span className="rank-meta">{c.player} · {c.role}</span>
              <span className="rank-num">{c.games} g</span>
              <span className="rank-n">{pct(c.wins / Math.max(1, c.games))} W</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

function PredictionAccuracy({ accuracy, action, phase }: {
  accuracy: PredictorAccuracy | null
  action: NextSlot['action']
  phase: NextSlot['phase']
}) {
  const scope = accuracy?.by_phase[phase]
  const team = scope?.team.top_3
  const baseline = scope?.league_popularity.top_3
  if (!accuracy || !team || !baseline) return null
  if (!team.sufficient_sample || !baseline.sufficient_sample || team.rate === null || baseline.rate === null) {
    return (
      <p className="evidence">
        Not enough evaluation evidence for {phase}: {team.slots} {action} slots; {accuracy.minimum_evaluation_slots} required.
      </p>
    )
  }
  return (
    <p className="evidence">
      Top-3 hit rate in {phase} on games from {accuracy.cutoff}: {pct(team.rate)} of {team.slots} {action} slots
      (league-popularity baseline: {pct(baseline.rate)}).
    </p>
  )
}

function TendencyList({ rows, games, onSelect, showPlayer }: { rows: TendencyRow[]; games: number; onSelect?: (id: string) => void; showPlayer?: boolean }) {
  if (rows.length === 0) return <p className="muted">No data.</p>
  return (
    <ol className="rank">
      {rows.map((r) => (
        <li key={r.champion_id}>
          <button className="rank-row" disabled={!onSelect} onClick={() => onSelect?.(r.champion_id)}>
            <span className="rank-name">{r.name}</span>
            {showPlayer && r.player ? <span className="rank-meta">{r.player}</span> : <Bar value={r.rate} />}
            <span className="rank-num">{pct(r.rate)}</span>
            <span className="rank-n">{r.count}/{games}</span>
          </button>
        </li>
      ))}
    </ol>
  )
}

function TendencyView({ opp, gameNumber, tendAll, tendGame }: { opp: string; gameNumber: number; tendAll: Tendencies | null; tendGame: Tendencies | null }) {
  const [scope, setScope] = useState<'game' | 'all'>('game')
  const t = scope === 'game' ? tendGame : tendAll
  return (
    <div className="pad">
      <div className="role-filter" role="group" aria-label="Scope">
        <button className={scope === 'game' ? 'chip chip-on' : 'chip'} onClick={() => setScope('game')}>Game {gameNumber}s only</button>
        <button className={scope === 'all' ? 'chip chip-on' : 'chip'} onClick={() => setScope('all')}>All games</button>
      </div>
      <p className="evidence">
        {t ? `${t.games} ${opp} games${scope === 'game' ? ` played as game ${gameNumber} of a series` : ''}.` : 'Loading…'}
        {t && t.games < 10 && ' Small sample: read as a hint, not a pattern.'}
      </p>
      <div className="two-col">
        <div>
          <h3 className="insight-title">Bans</h3>
          <TendencyList rows={(t?.bans ?? []).slice(0, 10)} games={t?.games ?? 0} />
        </div>
        <div>
          <h3 className="insight-title">Picks</h3>
          <TendencyList rows={(t?.picks ?? []).slice(0, 10)} games={t?.games ?? 0} showPlayer />
        </div>
      </div>
      <h3 className="insight-title">Banned against {opp}</h3>
      <p className="evidence">What opponents respect most.</p>
      <TendencyList rows={(t?.bans_against ?? []).slice(0, 6)} games={t?.games ?? 0} />
    </div>
  )
}

function PoolsView({ pools, teamNames, order }: { pools: Record<string, PlayerPool[]>; teamNames: Map<string, string>; order: string[] }) {
  return (
    <div className="pad">
      <p className="evidence">Most-played champions per current player. Struck-through champions are gone for this game (Fearless or drafted).</p>
      {order.map((teamId) => (
        <div key={teamId} className="pool-team">
          <h3 className="insight-title">{teamNames.get(teamId) ?? teamId}</h3>
          {(pools[teamId] ?? []).map((p) => {
            const open = p.champions.filter((c) => c.available).length
            return (
              <div key={p.player_id} className="pool-row">
                <div className="pool-player">
                  <strong>{p.name}</strong>
                  <span className="muted">{p.role}</span>
                  <span className={open <= 3 ? 'pool-left pool-low' : 'pool-left'}>{open}/{p.champions.length} open</span>
                </div>
                <ul className="pool-champs">
                  {p.champions.map((c) => (
                    <li key={c.champion_id} className={c.available ? 'pchip' : 'pchip pchip-off'} title={`${c.games} games, ${c.wins} wins`}>
                      {c.name} <span className="muted">{c.games}</span>
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
