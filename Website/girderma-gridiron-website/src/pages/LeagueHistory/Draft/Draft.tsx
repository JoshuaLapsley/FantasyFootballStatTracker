import React, { useEffect, useMemo, useRef, useState } from 'react';
import './Draft.css';

interface DraftPick {
  pick: number;
  round: number;
  manager_key: string;
  team_key: string;
  team_name: string;
  player_id: number;
  player_name: string;
  player_position: string;
  player_nfl_team: string;
  cost: number | null;
}

interface SubTabContentProps {
  year: string | number;
}

type ViewMode = 'board' | 'team';

const POSITION_COLORS: Record<string, { bg: string; text: string }> = {
  QB: { bg: '#E0E7FF', text: '#3730A3' },
  RB: { bg: '#D1FAE5', text: '#065F46' },
  WR: { bg: '#DBEAFE', text: '#1E40AF' },
  TE: { bg: '#FFEDD5', text: '#9A3412' },
  K: { bg: '#EDE9FE', text: '#5B21B6' },
  DEF: { bg: '#F3F4F6', text: '#374151' },
};

const getPosStyle = (pos: string) => POSITION_COLORS[pos] ?? { bg: '#F3F4F6', text: '#374151' };

const Draft: React.FC<SubTabContentProps> = ({ year }) => {
  const [picks, setPicks] = useState<DraftPick[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>('board');
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPicks(null);
    setError(null);

    import(`../../../league_stats_output/${year}/draft_${year}.json`)
      .then((mod) => {
        if (cancelled) return;
        const data: DraftPick[] = mod.default ?? mod;
        setPicks(data);
        if (data.length > 0) setSelectedTeam(data[0].team_key);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(`Couldn't load draft data for ${year}.`);
        console.error(err);
      });

    return () => {
      cancelled = true;
    };
  }, [year]);

  const { teamsInOrder, rounds, byRoundAndTeam, byTeam } = useMemo(() => {
    if (!picks) {
      return { teamsInOrder: [], rounds: [], byRoundAndTeam: new Map(), byTeam: new Map() };
    }

    const round1 = picks.filter((p) => p.round === 1).sort((a, b) => a.pick - b.pick);
    const teamsInOrder = round1.map((p) => ({ team_key: p.team_key, team_name: p.team_name }));

    const roundSet = new Set(picks.map((p) => p.round));
    const rounds = Array.from(roundSet).sort((a, b) => a - b);

    const byRoundAndTeam = new Map<string, DraftPick>();
    const byTeam = new Map<string, DraftPick[]>();

    picks.forEach((p) => {
      byRoundAndTeam.set(`${p.round}-${p.team_key}`, p);
      if (!byTeam.has(p.team_key)) byTeam.set(p.team_key, []);
      byTeam.get(p.team_key)!.push(p);
    });

    byTeam.forEach((list) => list.sort((a, b) => a.round - b.round));

    return { teamsInOrder, rounds, byRoundAndTeam, byTeam };
  }, [picks]);

  if (error) {
    return (
      <div className="draft-wrapper">
        <div className="draft-error-box">{error}</div>
      </div>
    );
  }

  if (!picks) {
    return (
      <div className="draft-wrapper">
        <div className="draft-loading">Loading {year} draft…</div>
      </div>
    );
  }

  return (
    <div className="draft-wrapper">
      <div className="draft-header">
        <div>
          <div className="draft-eyebrow">Draft Recap</div>
          <h2 className="draft-title">{year} Draft</h2>
        </div>
        <div className="toggle-group">
          <button
            onClick={() => setView('board')}
            className={`toggle-btn ${view === 'board' ? 'toggle-btn-active' : ''}`}
          >
            Full Board
          </button>
          <button
            onClick={() => setView('team')}
            className={`toggle-btn ${view === 'team' ? 'toggle-btn-active' : ''}`}
          >
            By Team
          </button>
        </div>
      </div>

      {view === 'board' ? (
        <BoardView teamsInOrder={teamsInOrder} rounds={rounds} byRoundAndTeam={byRoundAndTeam} />
      ) : (
        <TeamView
          teamsInOrder={teamsInOrder}
          byTeam={byTeam}
          selectedTeam={selectedTeam}
          onSelectTeam={setSelectedTeam}
        />
      )}
    </div>
  );
};

// ---------- Board View ----------

const BoardView: React.FC<{
  teamsInOrder: { team_key: string; team_name: string }[];
  rounds: number[];
  byRoundAndTeam: Map<string, DraftPick>;
}> = ({ teamsInOrder, rounds, byRoundAndTeam }) => {
  const topScrollRef = useRef<HTMLDivElement>(null);
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const [tableWidth, setTableWidth] = useState(0);
  const isSyncingRef = useRef(false);

  useEffect(() => {
    if (tableScrollRef.current) {
      setTableWidth(tableScrollRef.current.scrollWidth);
    }
  }, [teamsInOrder, rounds]);

  const handleTopScroll = () => {
    if (isSyncingRef.current) {
      isSyncingRef.current = false;
      return;
    }
    if (tableScrollRef.current && topScrollRef.current) {
      isSyncingRef.current = true;
      tableScrollRef.current.scrollLeft = topScrollRef.current.scrollLeft;
    }
  };

  const handleTableScroll = () => {
    if (isSyncingRef.current) {
      isSyncingRef.current = false;
      return;
    }
    if (tableScrollRef.current && topScrollRef.current) {
      isSyncingRef.current = true;
      topScrollRef.current.scrollLeft = tableScrollRef.current.scrollLeft;
    }
  };

  return (
    <div className="board-wrapper">
      <div className="top-scrollbar" ref={topScrollRef} onScroll={handleTopScroll}>
        <div className="top-scrollbar-spacer" style={{ width: tableWidth }} />
      </div>
      <div className="board-scroll" ref={tableScrollRef} onScroll={handleTableScroll}>
        <table className="draft-table">
          <thead>
            <tr>
              <th className="round-header-cell">Rd</th>
              {teamsInOrder.map((t) => (
                <th key={t.team_key} className="team-header-cell">
                  {t.team_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rounds.map((round) => (
              <tr key={round}>
                <td className="round-cell">{round}</td>
                {teamsInOrder.map((t) => {
                  const p = byRoundAndTeam.get(`${round}-${t.team_key}`);
                  if (!p) {
                    return (
                      <td key={t.team_key} className="pick-cell-empty">
                        —
                      </td>
                    );
                  }
                  const posStyle = getPosStyle(p.player_position);
                  return (
                    <td key={t.team_key} className="pick-cell">
                      <div className="pick-number">#{p.pick}</div>
                      <div className="player-name">{p.player_name}</div>
                      <div className="player-meta">
                        <span
                          className="pos-tag"
                          style={{ backgroundColor: posStyle.bg, color: posStyle.text }}
                        >
                          {p.player_position}
                        </span>
                        <span className="nfl-team">{p.player_nfl_team}</span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ---------- Team View ----------

const TeamView: React.FC<{
  teamsInOrder: { team_key: string; team_name: string }[];
  byTeam: Map<string, DraftPick[]>;
  selectedTeam: string | null;
  onSelectTeam: (teamKey: string) => void;
}> = ({ teamsInOrder, byTeam, selectedTeam, onSelectTeam }) => {
  const picks = selectedTeam ? byTeam.get(selectedTeam) ?? [] : [];

  return (
    <div>
      <div className="team-selector-row">
        {teamsInOrder.map((t) => (
          <button
            key={t.team_key}
            onClick={() => onSelectTeam(t.team_key)}
            className={`team-chip ${selectedTeam === t.team_key ? 'team-chip-active' : ''}`}
          >
            {t.team_name}
          </button>
        ))}
      </div>

      <div className="team-pick-list">
        {picks.map((p) => {
          const posStyle = getPosStyle(p.player_position);
          return (
            <div key={p.pick} className="team-pick-row">
              <div className="team-pick-round-badge">R{p.round}</div>
              <div className="team-pick-info">
                <div className="player-name">{p.player_name}</div>
                <div className="player-meta">
                  <span
                    className="pos-tag"
                    style={{ backgroundColor: posStyle.bg, color: posStyle.text }}
                  >
                    {p.player_position}
                  </span>
                  <span className="nfl-team">{p.player_nfl_team}</span>
                </div>
              </div>
              <div className="team-pick-overall">Pick #{p.pick}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Draft;