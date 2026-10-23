import React from 'react';

import './TradeEvaluator.css';

type Player = {
  player_id: string;
  player_name: string;
  position: string;
};

type WeekDetail = {
  net_gain: number;
  real_lineup_points: number;
  counterfactual_lineup_points: number;
};

type Side = {
  team_name: string;
  received: Player[];
  gave_up: Player[];
  weekly_net_gain: Record<string, number>;
  weekly_detail: Record<string, WeekDetail>;
  total_net_gain: number;
};

type Trade = {
  transaction_id: string;
  timestamp: number;
  traded_at: string;
  freeze_week: number;
  last_week_evaluated: number;
  sides: Record<string, Side>;
  weeks_skipped_no_projection_data: number[];
};

let trades: Trade[] | null = null;
try {
  trades = require('../../../league_stats_output/CurrentSeason/trade_evaluator_2026.json');
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

const PlayerList: React.FC<{ label: string; players: Player[] }> = ({ label, players }) => (
  <div className="te-players">
    <span className="te-players__label">{label}</span>
    <ul>
      {players.map((p) => (
        <li key={p.player_id}>
          <span className={`te-pos te-pos--${p.position}`}>{p.position}</span>
          {p.player_name}
        </li>
      ))}
    </ul>
  </div>
);

const SideCard: React.FC<{ side: Side; winner: boolean }> = ({ side, winner }) => {
  const weeks = Object.entries(side.weekly_detail).sort(([a], [b]) => Number(a) - Number(b));

  return (
    <section className={`te-side${winner ? ' te-side--winner' : ''}`}>
      <header className="te-side__head">
        <h4>{side.team_name}</h4>
        <div className={`te-total te-total--${tone(side.total_net_gain)}`}>
          <strong>{fmt(side.total_net_gain)}</strong>
          <span>total pts</span>
        </div>
      </header>

      <PlayerList label="Received" players={side.received} />
      <PlayerList label="Gave up" players={side.gave_up} />

      <table className="te-weeks">
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col">Actual</th>
            <th scope="col">Without trade</th>
            <th
              scope="col"
              title="Points scored with the trade minus points without it"
            >
              Net
            </th>
          </tr>
        </thead>
        <tbody>
          {weeks.map(([wk, d]) => (
            <tr key={wk}>
              <th scope="row">{wk}</th>
              <td>{d.real_lineup_points.toFixed(1)}</td>
              <td>{d.counterfactual_lineup_points.toFixed(1)}</td>
              <td>
                <span className={`te-net te-net--${tone(d.net_gain)}`}>{fmt(d.net_gain)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
};

const TradeCard: React.FC<{ trade: Trade }> = ({ trade }) => {
  const sides = Object.entries(trade.sides);
  const top = Math.max(...sides.map(([, s]) => s.total_net_gain));
  const even = sides.every(([, s]) => s.total_net_gain === top);
  const skipped = trade.weeks_skipped_no_projection_data;

  return (
    <article className="te-trade">
      <div className="te-trade__header">
        <h3>{sides.map(([, s]) => s.team_name).join(' & ')}</h3>
        <p>
          {fmtDate(trade.traded_at)} · frozen at week {trade.freeze_week} · evaluated through week{' '}
          {trade.last_week_evaluated}
        </p>
      </div>

      <div className="te-trade__sides">
        {sides.map(([teamKey, side]) => (
          <SideCard key={teamKey} side={side} winner={!even && side.total_net_gain === top} />
        ))}
      </div>

      {skipped.length > 0 && (
        <p className="te-skipped">Skipped (no projection data): week {skipped.join(', ')}</p>
      )}
    </article>
  );
};

const TradeEvaluator: React.FC = () => (
  <div className="te-page">
    {trades && trades.length > 0 ? (
      trades.map((t) => <TradeCard key={t.transaction_id} trade={t} />)
    ) : (
      <p className="te-empty">No trades available.</p>
    )}
  </div>
);

export default TradeEvaluator;
