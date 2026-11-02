import React from 'react';

import './TradeEvaluator.css';

type TradePlayer = {
  name: string;
  position: string;
  from_team: string;
  to_team: string;
};

type WeeklyPoints = {
  week: number;
  points_gained: number;
};

type Manager = {
  team: string;
  weekly_points_gained: WeeklyPoints[];
  net_points_gained: number;
  avg_points_gained_per_week: number;
};

type Trade = {
  transaction_id: string;
  date: string;
  players: TradePlayer[];
  managers: Manager[];
};

type TradeEvaluation = {
  year: number;
  trades: Trade[];
};

let trades: Trade[] | null = null;
try {
  const data: TradeEvaluation = require('../../../league_stats_output/2026/trade_evaluation.json');
  trades = data.trades;
} catch {
  trades = null;
}

const fmt = (n: number): string => (n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1));
const tone = (n: number): string => (n > 0 ? 'pos' : n < 0 ? 'neg' : 'flat');
const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

const PlayerList: React.FC<{ label: string; players: TradePlayer[] }> = ({ label, players }) => (
  <div className="te-players">
    <span className="te-players__label">{label}</span>
    <ul>
      {players.map((p) => (
        <li key={`${p.name}-${p.from_team}`}>
          <span className={`te-pos te-pos--${p.position}`}>{p.position}</span>
          {p.name}
        </li>
      ))}
    </ul>
  </div>
);

const SideCard: React.FC<{ manager: Manager; players: TradePlayer[]; winner: boolean }> = ({
  manager,
  players,
  winner,
}) => {
  const received = players.filter((p) => p.to_team === manager.team);
  const gaveUp = players.filter((p) => p.from_team === manager.team);
  const weeks = [...manager.weekly_points_gained].sort((a, b) => a.week - b.week);

  return (
    <section className={`te-side${winner ? ' te-side--winner' : ''}`}>
      <header className="te-side__head">
        <h4>{manager.team}</h4>
        <div className={`te-total te-total--${tone(manager.net_points_gained)}`}>
          <strong>{fmt(manager.net_points_gained)}</strong>
          <span>total pts</span>
        </div>
      </header>

      <PlayerList label="Received" players={received} />
      <PlayerList label="Gave up" players={gaveUp} />

      <table className="te-weeks">
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th
              scope="col"
              title="Points scored with the trade minus points without it"
            >
              Net
            </th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w.week}>
              <th scope="row">{w.week}</th>
              <td>
                <span className={`te-net te-net--${tone(w.points_gained)}`}>
                  {fmt(w.points_gained)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Avg</th>
            <td>
              <span className={`te-net te-net--${tone(manager.avg_points_gained_per_week)}`}>
                {fmt(manager.avg_points_gained_per_week)}
              </span>
            </td>
          </tr>
        </tfoot>
      </table>
    </section>
  );
};

const TradeCard: React.FC<{ trade: Trade }> = ({ trade }) => {
  const top = Math.max(...trade.managers.map((m) => m.net_points_gained));
  const even = trade.managers.every((m) => m.net_points_gained === top);
  const weeks = trade.managers.flatMap((m) => m.weekly_points_gained.map((w) => w.week));
  const firstWeek = weeks.length ? Math.min(...weeks) : null;
  const lastWeek = weeks.length ? Math.max(...weeks) : null;

  return (
    <article className="te-trade">
      <div className="te-trade__header">
        <h3>{trade.managers.map((m) => m.team).join(' & ')}</h3>
        <p>
          {fmtDate(trade.date)}
          {firstWeek !== null && lastWeek !== null && (
            <>
              {' '}
              · evaluated weeks {firstWeek}
              {lastWeek !== firstWeek ? `–${lastWeek}` : ''}
            </>
          )}
        </p>
      </div>

      <div className="te-trade__sides">
        {trade.managers.map((m) => (
          <SideCard
            key={m.team}
            manager={m}
            players={trade.players}
            winner={!even && m.net_points_gained === top}
          />
        ))}
      </div>
    </article>
  );
};

const TradeEvaluator: React.FC = () => (
  <>
    <header style={{ maxWidth: 640, margin: '0 auto 24px', textAlign: 'center' }}>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
        How trades are evaluated
      </h2>
      <p style={{ fontSize: 14, lineHeight: 1.6, color: '#6b7280' }}>
        We freeze both teams' rosters from the week the trade took effect. Each
        week after that, we compare two lineups for each team: the roster as it
        actually was, and the roster as it would have been without the trade.
        Both lineups start the players with the highest projections. If a slot
        has no available player, or the best option is projected below
        replacement level, a replacement-level player is used instead. The
        difference in points those starters actually scored is the trade's
        impact.
      </p>
    </header>
    <div className="te-page">
      {trades && trades.length > 0 ? (
        trades.map((t) => <TradeCard key={t.transaction_id} trade={t} />)
      ) : (
        <p className="te-empty">No trades available.</p>
      )}
    </div>
  </>
);

export default TradeEvaluator;
