import type { GameIn, OrderSlot } from '../api'

interface Props {
  teamId: string
  teamName: string
  side: 'blue' | 'red'
  game: GameIn
  order: OrderSlot[]
  names: Map<string, string>
  isC9: boolean
  hasFirstPick: boolean
}

/** One team's bans and picks for a game, in draft order, with the slot being drafted highlighted. */
export function TeamPanel({ teamId, teamName, side, game, order, names, isC9, hasFirstPick }: Props) {
  const nextSeq = game.actions.length + 1
  const slots = order
    .map((slot) => {
      const team = slot.who === 'first' ? game.first_pick_team : game.first_pick_team === game.blue_team ? game.red_team : game.blue_team
      return { ...slot, team }
    })
    .filter((slot) => slot.team === teamId)

  const render = (slot: (typeof slots)[number]) => {
    const value = game.actions[slot.seq - 1]
    const filled = slot.seq <= game.actions.length
    const active = slot.seq === nextSeq
    const label = filled ? (value ? names.get(value) ?? value : 'No ban') : ''
    return (
      <li
        key={slot.seq}
        className={`slot slot-${slot.action}${active ? ' slot-active' : ''}${filled ? ' slot-filled' : ''}`}
        aria-current={active ? 'step' : undefined}
      >
        <span className="slot-seq">{slot.seq}</span>
        <span className="slot-name">{label || (active ? `${slot.action === 'ban' ? 'Banning' : 'Picking'}…` : '')}</span>
      </li>
    )
  }

  return (
    <section className={`team-panel side-${side}`} aria-label={`${teamName} draft`}>
      <header className="team-header">
        <span className={`side-chip side-chip-${side}`}>{side === 'blue' ? 'Blue' : 'Red'}</span>
        <h2 className={isC9 ? 'team-name team-c9' : 'team-name'}>{teamName}</h2>
        {hasFirstPick && <span className="badge">First pick</span>}
      </header>
      <h3 className="slot-group-title">Bans</h3>
      <ol className="slot-list slot-list-bans">{slots.filter((s) => s.action === 'ban').map(render)}</ol>
      <h3 className="slot-group-title">Picks</h3>
      <ol className="slot-list">{slots.filter((s) => s.action === 'pick').map(render)}</ol>
    </section>
  )
}
