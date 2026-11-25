import React, { useEffect, useState } from 'react';


import PARDraftBoard from '../Components/StatPages/PARDraftBoard/PARDraftBoard';
import WARDraftBoard from '../Components/StatPages/WARDraftBoard/WARDraftBoard';
import EarnedWinsPlus from '../Components/StatPages/EarnedWinsPlus/EarnedWinsPlus';
import WARSurplus from '../Components/StatPages/WARSurplus/WARSurplus';
import WaiverWAR from '../Components/StatPages/WaiverWAR/WaiverWAR';
import WARAnalysis from '../Components/StatPages/WARAnalysis/WARAnalysis';
import TradeEvaluator from '../Components/StatPages/TradeEvaluator/TradeEvaluator';
import ScheduleSwap from '../Components/StatPages/ScheduleSwap/ScheduleSwap';
import TeamRankOverTime from '../Components/StatPages/TeamRankOverTime/TeamRankOverTime';
import EarnedWins from '../Components/StatPages/EarnedWins/EarnedWins';

// All Time views (unchanged)
import AllTimeWins from './AllTimeWins/AllTimeWins';
import AllTimePointsFor from './AllTimePointsFor/AllTimePointsFor';
import AllTimePointsAgainst from './AllTimePointsAgainst/AllTimePointsAgainst';
import PointsForByPlayer from './PointsForByPlayer/PointsForByPlayer';
import PointsAgainstByPlayer from './PointsAgainstByPlayer/PointsAgainstByPlayer';

// Reuses the CurrentSeason layout/dropdown styles (adjust the path as needed)
import '../CurrentSeason/CurrentSeason.css';
import Playoffs from './Playoffs/Playoffs';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Year = '2023' | '2024' | '2025' | 'All Time';

export interface SubTabContentProps {
  year: Year;
}

export interface SubTabConfig {
  header: string;
  Component: React.ComponentType<SubTabContentProps>;
}

interface ViewConfig {
  header: string;
  render: (year: Year) => React.ReactNode;
}

const YEARS: Year[] = ['2023', '2024', '2025', 'All Time'];

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

// Same list as CurrentSeason, each one rendered for the selected year
const SEASON_VIEWS: ViewConfig[] = [
  { header: 'Team Rank Over Time', render: (year) => <TeamRankOverTime year={year} /> },
  { header: 'Earned Wins', render: (year) => <EarnedWins year={year} /> },
  { header: 'Earned Wins Plus', render: (year) => <EarnedWinsPlus year={year} /> },
  { header: 'PAR Draft Board', render: (year) => <PARDraftBoard year={year} /> },
  { header: 'WAR Draft Board', render: (year) => <WARDraftBoard year={year} /> },
  { header: 'Surplus WAR Draft Board', render: (year) => <WARSurplus year={year} /> },
  { header: 'Waiver WAR', render: (year) => <WaiverWAR year={year} /> },
  { header: 'Draft WAR Analysis', render: (year) => <WARAnalysis year={year} /> },
  { header: 'Schedule Swap', render: (year) => <ScheduleSwap year={year} /> },
  { header: 'Trade Evaluator', render: (year) => <TradeEvaluator year={year} /> },
  { header: 'Playoffs', render: (year) => <Playoffs year={year} /> },
];

const SUB_TABS_ALL_TIME: SubTabConfig[] = [
  { header: 'All Time Wins', Component: AllTimeWins },
  { header: 'All Time Points For', Component: AllTimePointsFor },
  { header: 'All Time Points Against', Component: AllTimePointsAgainst },
  { header: 'Points For By Player', Component: PointsForByPlayer },
  { header: 'Points Against By Player', Component: PointsAgainstByPlayer },
];

const ALL_TIME_VIEWS: ViewConfig[] = SUB_TABS_ALL_TIME.map(({ header, Component }) => ({
  header,
  render: (year) => <Component year={year} />,
}));

const getViews = (year: Year): ViewConfig[] =>
  year === 'All Time' ? ALL_TIME_VIEWS : SEASON_VIEWS;

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const RankDashboard: React.FC = () => {
  const [year, setYear] = useState<Year>(YEARS[0]);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const isAllTime = year === 'All Time';
  const views = getViews(year);
  const index = Math.min(selectedIndex, views.length - 1);
  const selectedView = views[index];


  const handleYearChange = (next: Year) => {
    // The season and All Time lists are different, so start over when switching between them
    if ((next === 'All Time') !== isAllTime) setSelectedIndex(0);
    setYear(next);
  };

  return (
    <main className="current-season">
      <header className="current-season__header">
        <h1>League History</h1>
      </header>

      <section className="current-season__controls">
        <label htmlFor="history-year" className="current-season__label">
          Select a year
        </label>

        <select
          id="history-year"
          className="current-season__select"
          value={year}
          onChange={(event) => handleYearChange(event.target.value as Year)}
        >
          {YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        <label htmlFor="history-view" className="current-season__label">
          Select a view
        </label>

        <select
          id="history-view"
          className="current-season__select"
          value={index}
          onChange={(event) => setSelectedIndex(Number(event.target.value))}
        >
          {views.map((view, i) => (
            <option key={view.header} value={i}>
              {view.header}
            </option>
          ))}
        </select>
      </section>

      <section className="current-season__content">
        {/* key resets each page's filters and sorting when the year or view changes */}
        <div className="current-season__component" key={`${year}-${selectedView.header}`}>
          {selectedView.render(year)}
        </div>
      </section>
    </main>
  );
};

export default RankDashboard;