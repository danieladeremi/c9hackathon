import { useMemo, useState } from 'react'
import { ROLES, type Champion, type Role } from '../api'

interface Props {
  champions: Champion[]
  unavailable: Record<string, string>
  fearless: Record<string, { game: number; team_id: string }>
  disabled: boolean
  onSelect: (championId: string) => void
}

/** Searchable champion list. Unavailable champions stay visible, dimmed, with the reason. */
export function ChampionGrid({ champions, unavailable, fearless, disabled, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [role, setRole] = useState<Role | 'all'>('all')
  const [hideUnavailable, setHideUnavailable] = useState(false)

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return champions.filter(
      (c) =>
        (role === 'all' || c.main_role === role) &&
        (!q || c.name.toLowerCase().includes(q)) &&
        !(hideUnavailable && unavailable[c.champion_id]),
    )
  }, [champions, query, role, hideUnavailable, unavailable])

  return (
    <section className="champion-grid" aria-label="Champions">
      <div className="grid-controls">
        <input
          type="search"
          placeholder="Search champions"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search champions"
        />
        <div className="role-filter" role="group" aria-label="Filter by role">
          {(['all', ...ROLES] as const).map((r) => (
            <button key={r} className={role === r ? 'chip chip-on' : 'chip'} onClick={() => setRole(r)}>
              {r === 'all' ? 'All' : r[0].toUpperCase() + r.slice(1)}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={hideUnavailable} onChange={(e) => setHideUnavailable(e.target.checked)} />
          Hide unavailable
        </label>
      </div>
      <ul className="grid">
        {shown.map((c) => {
          const reason = unavailable[c.champion_id]
          const lockedIn = fearless[c.champion_id]
          return (
            <li key={c.champion_id}>
              <button
                className={`champ${reason ? ' champ-off' : ''}${lockedIn ? ' champ-fearless' : ''}`}
                disabled={disabled || Boolean(reason)}
                title={reason ? `${c.name}: ${reason}` : `${c.name} · ${c.games} pro games · ${Math.round(c.win_rate * 100)}% win rate`}
                onClick={() => onSelect(c.champion_id)}
              >
                <span className="champ-name">{c.name}</span>
                {lockedIn ? <span className="champ-tag">G{lockedIn.game}</span> : <span className="champ-games">{c.games}</span>}
              </button>
            </li>
          )
        })}
      </ul>
      {shown.length === 0 && <p className="muted">No champions match.</p>}
    </section>
  )
}
