import { useEffect, useMemo, useState } from 'react'
import { api, C9_TEAM_ID, type Champion, type DraftState, type OrderSlot, type PredictorAccuracy, type SeriesIn, type Team, type Tendencies } from './api'
import { ChampionGrid } from './components/ChampionGrid'
import { Insights } from './components/Insights'
import { TeamPanel } from './components/TeamPanel'
import { c9Side, GAMES_IN, isDecided, loadSeries, newSeries, nextGame, saveSeries, setSetup, wins, withGame } from './series'

const PHASE_LABEL = { ban1: 'Ban phase 1', pick1: 'Pick phase 1', ban2: 'Ban phase 2', pick2: 'Pick phase 2' } as const

export default function App() {
  const [teams, setTeams] = useState<Team[]>([])
  const [champions, setChampions] = useState<Champion[]>([])
  const [order, setOrder] = useState<OrderSlot[]>([])
  const [series, setSeries] = useState<SeriesIn | null>(() => loadSeries())
  const [viewIndex, setViewIndex] = useState<number | null>(null)
  const [state, setState] = useState<DraftState | null>(null)
  const [tendAll, setTendAll] = useState<Tendencies | null>(null)
  const [tendGame, setTendGame] = useState<Tendencies | null>(null)
  const [predictorAccuracy, setPredictorAccuracy] = useState<PredictorAccuracy | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.teams(), api.champions(), api.order()])
      .then(([t, c, o]) => {
        setTeams(t)
        setChampions(c)
        setOrder(o)
      })
      .catch((e: Error) => setError(`Can't reach the API (${e.message}). Start it with: uv run uvicorn planner.api:app --port 8000`))
  }, [])

  useEffect(() => {
    api.predictorAccuracy().then(setPredictorAccuracy).catch(() => setPredictorAccuracy(null))
  }, [])

  useEffect(() => saveSeries(series), [series])

  useEffect(() => {
    if (!series) return
    let live = true
    api
      .draftState(series)
      .then((s) => live && (setState(s), setError(null)))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [series])

  const lastIndex = series ? series.games.length - 1 : 0
  const index = viewIndex ?? lastIndex
  const gameNumber = index + 1
  const opponent = series?.team_b ?? ''

  useEffect(() => {
    if (!opponent) return
    api.tendencies(opponent).then(setTendAll).catch(() => setTendAll(null))
  }, [opponent])
  useEffect(() => {
    if (!opponent) return
    api.tendencies(opponent, gameNumber).then(setTendGame).catch(() => setTendGame(null))
  }, [opponent, gameNumber])

  const teamNames = useMemo(() => new Map(teams.map((t) => [t.team_id, t.name])), [teams])
  const champNames = useMemo(() => new Map(champions.map((c) => [c.champion_id, c.name])), [champions])

  if (!series) {
    return <SetupScreen teams={teams} error={error} onStart={(s) => (setSeries(s), setViewIndex(null))} />
  }

  const game = series.games[index]
  const gameState = state?.games[index]
  const next = gameState?.next ?? null
  const editable = index === lastIndex
  const complete = game.actions.length === order.length && order.length > 0
  const score = wins(series)
  const decided = isDecided(series)
  const c9 = teamNames.get(C9_TEAM_ID) ?? 'Cloud9 Kia'
  const oppName = teamNames.get(opponent) ?? 'Opponent'

  const update = (change: (s: SeriesIn) => SeriesIn) => setSeries((s) => (s ? change(s) : s))
  const record = (championId: string | null) => {
    if (!editable || complete) return
    if (championId && gameState?.unavailable[championId]) {
      setError(`${champNames.get(championId)} is unavailable: ${gameState.unavailable[championId]}`)
      return
    }
    update((s) => withGame(s, index, (g) => ({ ...g, actions: [...g.actions, championId] })))
  }
  const undo = () =>
    update((s) => {
      const g = s.games[lastIndex]
      if (g.winner) return withGame(s, lastIndex, (x) => ({ ...x, winner: null }))
      if (g.actions.length) return withGame(s, lastIndex, (x) => ({ ...x, actions: x.actions.slice(0, -1) }))
      if (lastIndex > 0) return { ...s, games: s.games.slice(0, -1) }
      return s
    })

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span>Draft Planner</span>
        </div>
        <div className="matchup">
          <span className="team-c9">{c9}</span>
          <span className="score">
            {score[C9_TEAM_ID] ?? 0} – {score[opponent] ?? 0}
          </span>
          <span>{oppName}</span>
          <span className="muted">{series.format.toUpperCase()} · Fearless</span>
        </div>
        <button className="ghost" onClick={() => confirm('Start a new series? The current one will be cleared.') && (setSeries(null), setState(null))}>
          New series
        </button>
      </header>

      <nav className="game-tabs" aria-label="Games">
        {series.games.map((g, i) => (
          <button key={i} className={i === index ? 'gtab gtab-on' : 'gtab'} onClick={() => setViewIndex(i === lastIndex ? null : i)}>
            Game {i + 1}
            {g.winner && <span className={g.winner === C9_TEAM_ID ? 'gtab-w' : 'gtab-l'}>{g.winner === C9_TEAM_ID ? 'W' : 'L'}</span>}
          </button>
        ))}
        {Array.from({ length: GAMES_IN[series.format] - series.games.length }, (_, i) => (
          <span key={`f${i}`} className="gtab gtab-future">Game {series.games.length + i + 1}</span>
        ))}
      </nav>

      {error && (
        <div className="error" role="alert">
          {error} <button className="ghost" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="game-setup">
        <GameSetup
          disabled={!editable || game.actions.length > 0}
          side={c9Side(game)}
          c9First={game.first_pick_team === C9_TEAM_ID}
          onChange={(side, first) => update((s) => withGame(s, index, (g) => setSetup(g, opponent, side, first)))}
        />
        <div className="slot-banner" aria-live="polite">
          {next ? (
            <>
              <span className="muted">Slot {next.seq}/20 · {PHASE_LABEL[next.phase]}</span>
              <strong className={next.team_id === C9_TEAM_ID ? 'team-c9' : ''}>
                {teamNames.get(next.team_id)} {next.action === 'ban' ? 'bans' : 'picks'}
              </strong>
            </>
          ) : complete ? (
            <strong>Draft complete</strong>
          ) : (
            <span className="muted">Loading…</span>
          )}
        </div>
        <div className="actions">
          {editable && next?.action === 'ban' && <button className="ghost" onClick={() => record(null)}>Skip ban</button>}
          {editable && <button className="ghost" onClick={undo} disabled={series.games.length === 1 && game.actions.length === 0}>Undo</button>}
          {editable && complete && !game.winner && (
            <>
              <span className="muted">Winner:</span>
              <button onClick={() => update((s) => withGame(s, index, (g) => ({ ...g, winner: C9_TEAM_ID })))}>{c9}</button>
              <button onClick={() => update((s) => withGame(s, index, (g) => ({ ...g, winner: opponent })))}>{oppName}</button>
            </>
          )}
          {editable && game.winner && !decided && (
            <button className="primary" onClick={() => update((s) => ({ ...s, games: [...s.games, nextGame(s)] }))}>
              Draft game {series.games.length + 1}
            </button>
          )}
          {decided && <strong>{(score[C9_TEAM_ID] ?? 0) > (score[opponent] ?? 0) ? `${c9} win the series` : `${oppName} win the series`}</strong>}
        </div>
      </div>

      <main className="board">
        <TeamPanel
          teamId={game.blue_team}
          teamName={teamNames.get(game.blue_team) ?? ''}
          side="blue"
          game={game}
          order={order}
          names={champNames}
          isC9={game.blue_team === C9_TEAM_ID}
          hasFirstPick={game.first_pick_team === game.blue_team}
        />
        <ChampionGrid
          champions={champions}
          unavailable={gameState?.unavailable ?? {}}
          fearless={gameState?.fearless_locked ?? {}}
          disabled={!editable || complete}
          onSelect={record}
        />
        <TeamPanel
          teamId={game.red_team}
          teamName={teamNames.get(game.red_team) ?? ''}
          side="red"
          game={game}
          order={order}
          names={champNames}
          isC9={game.red_team === C9_TEAM_ID}
          hasFirstPick={game.first_pick_team === game.red_team}
        />
        <Insights
          next={editable ? next : null}
          c9Id={C9_TEAM_ID}
          opponentId={opponent}
          teamNames={teamNames}
          gameNumber={gameNumber}
          unavailable={gameState?.unavailable ?? {}}
          tendAll={tendAll}
          tendGame={tendGame}
          pools={state?.pools ?? {}}
          accuracy={predictorAccuracy}
          series={series}
          gameIndex={index}
          champions={champions}
          order={order}
          onSelect={record}
        />
      </main>
      <footer className="footer muted">
        Match data provided by GRID. Not endorsed by Riot Games. Every figure shows its sample size.
      </footer>
    </div>
  )
}

function GameSetup({ disabled, side, c9First, onChange }: { disabled: boolean; side: 'blue' | 'red'; c9First: boolean; onChange: (side: 'blue' | 'red', c9First: boolean) => void }) {
  return (
    <div className="setup" title={disabled ? 'Set before the first ban' : undefined}>
      <span className="muted">C9 side</span>
      <div className="seg">
        <button disabled={disabled} className={side === 'blue' ? 'seg-on seg-blue' : ''} onClick={() => onChange('blue', c9First)}>Blue</button>
        <button disabled={disabled} className={side === 'red' ? 'seg-on seg-red' : ''} onClick={() => onChange('red', c9First)}>Red</button>
      </div>
      <span className="muted">First pick</span>
      <div className="seg">
        <button disabled={disabled} className={c9First ? 'seg-on' : ''} onClick={() => onChange(side, true)}>C9</button>
        <button disabled={disabled} className={!c9First ? 'seg-on' : ''} onClick={() => onChange(side, false)}>Opponent</button>
      </div>
    </div>
  )
}

function SetupScreen({ teams, error, onStart }: { teams: Team[]; error: string | null; onStart: (s: SeriesIn) => void }) {
  const options = useMemo(() => {
    const lcs = (t: Team) => (t.last_event.startsWith('LCS') ? 0 : 1)
    return teams.filter((t) => t.team_id !== C9_TEAM_ID).sort((a, b) => lcs(a) - lcs(b) || b.games - a.games)
  }, [teams])
  const [opponent, setOpponent] = useState('')
  const [format, setFormat] = useState<SeriesIn['format']>('bo5')
  const chosen = opponent || options[0]?.team_id || ''

  return (
    <div className="setup-screen">
      <div className="setup-card">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span>Draft Planner</span>
        </div>
        <h1>Plan a Fearless series</h1>
        <p className="muted">Step through every pick and ban against an opponent, with their real draft history beside each slot.</p>
        {error && <div className="error" role="alert">{error}</div>}
        <label className="field">
          Opponent
          <select value={chosen} onChange={(e) => setOpponent(e.target.value)}>
            {options.map((t) => (
              <option key={t.team_id} value={t.team_id}>
                {t.name} · {t.games} games · {t.last_event}
              </option>
            ))}
          </select>
        </label>
        <div className="field">
          Format
          <div className="seg">
            {(['bo1', 'bo3', 'bo5'] as const).map((f) => (
              <button key={f} className={format === f ? 'seg-on' : ''} onClick={() => setFormat(f)}>{f.toUpperCase()}</button>
            ))}
          </div>
        </div>
        <button className="primary big" disabled={!chosen} onClick={() => onStart(newSeries(chosen, format))}>
          Start draft
        </button>
      </div>
    </div>
  )
}
