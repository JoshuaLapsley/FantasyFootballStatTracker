import React, { useState } from 'react';

import SimulatedPlayoffOdds from '../Components/StatPages/SimulatedPlayoffOdds/SimulatedPlayoffOdds';
import SimulatedRecordDistribution from '../Components/StatPages/SimulatedRecordDistriubtion/SimulatedRecordDistribution';
import PARDraftBoard from '../Components/StatPages/PARDraftBoard/PARDraftBoard';
import WARDraftBoard from '../Components/StatPages/WARDraftBoard/WARDraftBoard';
import EarnedWinsPlus from '../Components/StatPages/EarnedWinsPlus/EarnedWinsPlus';

import './CurrentSeason.css';
import WARSurplus from '../Components/StatPages/WARSurplus/WARSurplus';
import WaiverWAR from '../Components/StatPages/WaiverWAR/WaiverWAR';
import WARAnalysis from '../Components/StatPages/WARAnalysis/WARAnalysis';
import meta from '../../league_stats_output/2026/meta.json';
import TradeEvaluator from '../Components/StatPages/TradeEvaluator/TradeEvaluator';
import ScheduleSwap from '../Components/StatPages/ScheduleSwap/ScheduleSwap';
import SimulatedConditions from '../Components/StatPages/SimulatedConditions/SimulatedConditions';
import ProjectedTeamPoints from '../Components/StatPages/ProjectedTeamPoints/ProjectedTeamPoints';
import TeamRankOverTime from '../Components/StatPages/TeamRankOverTime/TeamRankOverTime';
import EarnedWins from '../Components/StatPages/EarnedWins/EarnedWins';

interface TabConfig {
  header: string;
  Component: React.ComponentType;
}

const year = 2026;

const CURRENT_SEASON_TABS: TabConfig[] = [
  { header: 'Team Rank Over Time', Component: () => <TeamRankOverTime year={year} /> },
  { header: 'Earned Wins', Component: () => <EarnedWins year={year} /> },
  { header: 'Earned Wins Plus', Component: () => <EarnedWinsPlus year={year} /> },
  { header: 'PAR Draft Board', Component: () => <PARDraftBoard year={year} /> },
  { header: 'WAR Draft Board', Component: () => <WARDraftBoard year={year} /> },
  { header: 'Surplus WAR Draft Board', Component: () => <WARSurplus year={year} /> },
  { header: 'Waiver WAR', Component: () => <WaiverWAR year={year} /> },
  { header: 'Draft WAR Analysis', Component: () => <WARAnalysis year={year} /> },
  { header: 'Schedule Swap', Component: () => <ScheduleSwap year={year} /> },
  { header: 'Trade Evaluator', Component: () => <TradeEvaluator year={year} /> },
  { header: 'Simulated Playoff Odds', Component: () => <SimulatedPlayoffOdds year={year} /> },
  { header: 'Simulated Record Distribution', Component: () => <SimulatedRecordDistribution year={year} /> },
  { header: 'Simulated Conditions', Component: () => <SimulatedConditions year={year} /> },
  { header: 'Projected Team Points', Component: () => <ProjectedTeamPoints year={year} /> },

];



  // 
const CurrentSeason: React.FC = () => {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const SelectedComponent = CURRENT_SEASON_TABS[selectedIndex].Component;

  return (
    <main className="current-season">
      <header className="current-season__header">
        <h1>Current Season</h1>
        <span className="current-season__updated">
          Updated through Week {meta.data_through_week}
        </span>
      </header>

      <section className="current-season__controls">
        <label htmlFor="season-view" className="current-season__label">
          Select a view
        </label>

        <select
          id="season-view"
          className="current-season__select"
          value={selectedIndex}
          onChange={(event) => setSelectedIndex(Number(event.target.value))}
        >
          {CURRENT_SEASON_TABS.map((tab, index) => (
            <option key={tab.header} value={index}>
              {tab.header}
            </option>
          ))}
        </select>
      </section>

      <section className="current-season__content">

        <div className="current-season__component">
          <SelectedComponent />
        </div>
      </section>
    </main>
  );
};

export default CurrentSeason;