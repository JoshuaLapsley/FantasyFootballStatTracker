
import React, { useMemo, useState } from 'react';
import draftValueData from '../../../league_stats_output/CurrentSeason/draft_value_2026.json';
import './WARAnalysis.css';

type DraftValue = {
    pick: number;
    round: number;
    player_id: string;
    player_name: string;
    position: string;
    drafted_by: string;
    actual_war: number;
    expected_war_full_season: number;
    expected_war_prorated: number;
    expected_war: number;
    surplus_war: number;
    weeks_completed?: number;
    full_season_weeks?: number;
};

type SortMetric =
    | 'pick'
    | 'actual_war'
    | 'expected_war'
    | 'surplus_war';

const draftValues = draftValueData as DraftValue[];

const WARAnalysis: React.FC = () => {
    const [position, setPosition] = useState('All');
    const [sortMetric, setSortMetric] =
        useState<SortMetric>('surplus_war');
    const [sortDirection, setSortDirection] =
        useState<'asc' | 'desc'>('desc');
    const [search, setSearch] = useState('');

    const positions = useMemo(() => {
        return [
            'All',
            ...Array.from(
                new Set(draftValues.map(player => player.position))
            ).sort()
        ];
    }, []);

    // Filter and sort players without applying the text search.
    // These positions determine each player's rank.
    const rankedPlayers = useMemo(() => {
        return draftValues
            .filter(player =>
                position === 'All' || player.position === position
            )
            .sort((a, b) => {
                const difference = a[sortMetric] - b[sortMetric];

                return sortDirection === 'asc'
                    ? difference
                    : -difference;
            });
    }, [position, sortMetric, sortDirection]);

    // Create a rank lookup so text search never changes a player's rank.
    const playerRanks = useMemo(() => {
        const ranks = new Map<string, number>();

        rankedPlayers.forEach((player, index) => {
            ranks.set(
                `${player.player_id}-${player.pick}`,
                index + 1
            );
        });

        return ranks;
    }, [rankedPlayers]);

    // Apply text search only to the displayed rows.
    const filteredPlayers = useMemo(() => {
        const searchTerm = search.trim().toLowerCase();

        return rankedPlayers.filter(player => {
            return (
                player.player_name.toLowerCase().includes(searchTerm) ||
                player.drafted_by.toLowerCase().includes(searchTerm)
            );
        });
    }, [rankedPlayers, search]);

    const formatWar = (value: number) => value.toFixed(3);

    return (
        <div className="draft-value-table">
            <h2>WAR Analysis</h2>

            <p className="draft-value-table__description">
                Filter on WAR metrics. (NOTE: This currently only includes
                drafted players; future versions will account for all players.)
            </p>

            <div className="draft-value-table__filters">
                <label>
                    Position
                    <select
                        value={position}
                        onChange={event => setPosition(event.target.value)}
                    >
                        {positions.map(pos => (
                            <option key={pos} value={pos}>
                                {pos}
                            </option>
                        ))}
                    </select>
                </label>

                <label>
                    Sort by
                    <select
                        value={sortMetric}
                        onChange={event =>
                            setSortMetric(event.target.value as SortMetric)
                        }
                    >
                        <option value="surplus_war">Surplus WAR</option>
                        <option value="actual_war">Actual WAR</option>
                        <option value="expected_war">Expected WAR</option>
                        <option value="pick">Draft Pick</option>
                    </select>
                </label>

                <label>
                    Order
                    <select
                        value={sortDirection}
                        onChange={event =>
                            setSortDirection(
                                event.target.value as 'asc' | 'desc'
                            )
                        }
                    >
                        <option value="desc">Decreasing</option>
                        <option value="asc">Increasing</option>
                    </select>
                </label>

                <label className="draft-value-table__search">
                    Search player or manager
                    <input
                        type="text"
                        value={search}
                        onChange={event => setSearch(event.target.value)}
                        placeholder="e.g. Kimani Vidal or Josh"
                    />
                </label>
            </div>

            <div className="draft-value-table__result-count">
                Showing {filteredPlayers.length} of {rankedPlayers.length} picks
            </div>

            <div className="draft-value-table__scroll">
                <table>
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Pick</th>
                            <th>Round</th>
                            <th>Player</th>
                            <th>Position</th>
                            <th>Manager</th>
                            <th>Actual WAR</th>
                            <th>Expected WAR</th>
                            <th>Surplus WAR</th>
                        </tr>
                    </thead>

                    <tbody>
                        {filteredPlayers.map(player => {
                            const rank = playerRanks.get(
                                `${player.player_id}-${player.pick}`
                            );

                            return (
                                <tr
                                    key={`${player.player_id}-${player.pick}`}
                                >
                                    <td>{rank ?? '-'}</td>
                                    <td>{player.pick}</td>
                                    <td>{player.round}</td>

                                    <td className="draft-value-table__player">
                                        {player.player_name}
                                    </td>

                                    <td>{player.position}</td>
                                    <td>{player.drafted_by}</td>
                                    <td>{formatWar(player.actual_war)}</td>
                                    <td>{formatWar(player.expected_war)}</td>

                                    <td
                                        className={
                                            player.surplus_war > 0
                                                ? 'draft-value-table__positive'
                                                : player.surplus_war < 0
                                                    ? 'draft-value-table__negative'
                                                    : ''
                                        }
                                    >
                                        {formatWar(player.surplus_war)}
                                    </td>
                                </tr>
                            );
                        })}

                        {filteredPlayers.length === 0 && (
                            <tr>
                                <td
                                    colSpan={9}
                                    className="draft-value-table__empty"
                                >
                                    No draft picks match these filters.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default WARAnalysis;
