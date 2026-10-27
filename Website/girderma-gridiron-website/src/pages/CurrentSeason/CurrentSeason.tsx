import React, { useState } from 'react';

import EarnedWins from './EarnedWins/EarnedWins';
import SimulatedPlayoffOdds from './SimulatedPlayoffOdds/SimulatedPlayoffOdds';
import SimulatedRecordDistribution from './SimulatedRecordDistriubtion/SimulatedPlayoffOdds';
import PARDraftBoard from './PARDraftBoard/PARDraftBoard';
import WARDraftBoard from './WARDraftBoard/WARDraftBoard';
import EarnedWinsPlus from './EarnedWinsPlus/EarnedWinsPlus';

import './CurrentSeason.css';
import WARSurplus from './WARSurplus/WARSurplus';
import WaiverWAR from './WaiverWAR/WaiverWAR';
import WARAnalysis from './WARAnalysis/WARAnalysis';
import meta from '../../league_stats_output/CurrentSeason/meta.json';
import TradeEvaluator from './TradeEvaluator/TradeEvaluator';
import ScheduleSwap from './ScheduleSwap/ScheduleSwap';

interface TabConfig {
  header: string;
  Component: React.ComponentType;
}

const CURRENT_SEASON_TABS: TabConfig[] = [
  { header: 'Earned Wins', Component: EarnedWins },
  { header: 'Earned Wins Plus', Component: EarnedWinsPlus },
  { header: 'Simulated Playoff Odds', Component: SimulatedPlayoffOdds },
  { header: 'Simulated Record Distribution', Component: SimulatedRecordDistribution },
  { header: 'PAR Draft Board', Component: PARDraftBoard },
  { header: 'WAR Draft Board', Component: WARDraftBoard },
  { header: 'Surplus WAR Draft Board', Component: WARSurplus },
  { header: 'Waiver WAR', Component: WaiverWAR },
  { header: 'WAR Analysis', Component: WARAnalysis },

];
  // { header: 'Trade Evaluator', Component: TradeEvaluator },
  // { header: 'Schedule Swap', Component: ScheduleSwap },
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