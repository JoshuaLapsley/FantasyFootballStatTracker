import React, { useMemo, useState } from 'react';
import draftValueData from '../../../league_stats_output/CurrentSeason/draft_value_2026.json';
import meta from '../../../league_stats_output/CurrentSeason/meta.json';
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
    bye_week?: number | null;
};

type SortMetric =
    | 'pick'
    | 'actual_war'
    | 'expected_war'
    | 'surplus_war';

type ByeFilter = 'all' | 'pending' | 'passed';

const draftValues = draftValueData as DraftValue[];

const currentWeek: number = meta.current_week;
const lateSeason = currentWeek >= 10;

// Bye hasn't happened yet (it's this week or later)
const byeStillPending = (player: DraftValue) =>
    player.bye_week != null && player.bye_week >= currentWeek;

// Bye has already happened
const byeAlreadyHappened = (player: DraftValue) =>
    player.bye_week != null && player.bye_week < currentWeek;

// Before week 10: * on players who've had their bye.
// Week 10 and later: * on players who haven't had it yet.
const showsAsterisk = (player: DraftValue) =>
    lateSeason ? byeStillPending(player) : byeAlreadyHappened(player);

const WARAnalysis: React.FC = () => {
    const [position, setPosition] = useState('All');
    const [sortMetric, setSortMetric] =
        useState<SortMetric>('surplus_war');
    const [sortDirection, setSortDirection] =
        useState<'asc' | 'desc'>('desc');
    const [search, setSearch] = useState('');
    const [byeFilter, setByeFilter] = useState<ByeFilter>('all');

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

    // Apply text search and bye filter only to the displayed rows.
    const filteredPlayers = useMemo(() => {
        const searchTerm = search.trim().toLowerCase();

        return rankedPlayers.filter(player => {
            const matchesSearch =
                player.player_name.toLowerCase().includes(searchTerm) ||
                player.drafted_by.toLowerCase().includes(searchTerm);

            const matchesBye =
                byeFilter === 'all' ||
                (byeFilter === 'pending' && byeStillPending(player)) ||
                (byeFilter === 'passed' && byeAlreadyHappened(player));

            return matchesSearch && matchesBye;
        });
    }, [rankedPlayers, search, byeFilter]);

    const formatWar = (value: number) => value.toFixed(3);

    return (
        <div className="draft-value-table">
            <h2>WAR Analysis</h2>

            <p className="draft-value-table__description">
                Filter on WAR metrics. (NOTE: This currently only includes
                drafted players; future versions will account for all players.)
            </p>

            <p className="draft-value-table__note">
                {lateSeason
                    ? "* This player hasn't had their bye week yet, so they've played more games than players who already had theirs. Their WAR totals may look inflated until the bye passes."
                    : "* This player has already had their bye week, so they've played one fewer game than players who haven't had theirs yet. Their WAR totals may look low."}
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

                <label>
                    Bye week
                    <select
                        value={byeFilter}
                        onChange={event =>
                            setByeFilter(event.target.value as ByeFilter)
                        }
                    >
                        <option value="all">All players</option>
                        <option value="pending">Bye still pending</option>
                        <option value="passed">Bye already happened</option>
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
                                        {showsAsterisk(player) && (
                                            <span
                                                className="draft-value-table__bye-flag"
                                                title={
                                                    lateSeason
                                                        ? `Bye (week ${player.bye_week}) hasn't happened yet`
                                                        : `Already had bye (week ${player.bye_week})`
                                                }
                                            >
                                                *
                                            </span>
                                        )}
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