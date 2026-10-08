import React from 'react';
import {
  TabComponent,
  TabItemsDirective,
  TabItemDirective
} from '@syncfusion/ej2-react-navigations';

// Required Syncfusion styles
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-buttons/styles/material.css';
import '@syncfusion/ej2-navigations/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';

// Import your tab components here
import EarnedWins from './EarnedWins/EarnedWins';
import SimulatedPlayoffOdds from './SimulatedPlayoffOdds/SimulatedPlayoffOdds';
import SimulatedRecordDistribution from './SimulatedRecordDistriubtion/SimulatedPlayoffOdds';
import PARDraftBoard from './PARDraftBoard/PARDraftBoard';
import WARDraftBoard from './WARDraftBoard/WARDraftBoard';
import EarnedWinsPlus from './EarnedWinsPlus/EarnedWinsPlus';


// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TabConfig {
  header: string;
  Component: React.ComponentType;
}

// ---------------------------------------------------------------------------
// Current Season Tabs
// ---------------------------------------------------------------------------

const CURRENT_SEASON_TABS: TabConfig[] = [
  { header: 'Earned Wins', Component: EarnedWins },
  { header: 'Earned Wins Plus', Component: EarnedWinsPlus },
  { header: 'Simulated Playoff Odds', Component: SimulatedPlayoffOdds },
  { header: 'Simulated Record Distribution', Component: SimulatedRecordDistribution },
  { header: 'PAR Draft Board', Component: PARDraftBoard },
  { header: 'WAR Draft Board', Component: WARDraftBoard },
];

// ---------------------------------------------------------------------------
// Current Season
// ---------------------------------------------------------------------------

const CurrentSeason: React.FC = () => {
  return (
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ padding: '20px', width: '100%' }}>

        <h2 style={{ textAlign: 'center' }}>Current Season</h2>

        <TabComponent
          heightAdjustMode="Auto"
          overflowMode="Scrollable"
          swipeMode="None"
        >
          <TabItemsDirective>
            {CURRENT_SEASON_TABS.map(({ header, Component }) => (
              <TabItemDirective
                key={header}
                header={{ text: header }}
                content={() => <Component />}
              />
            ))}
          </TabItemsDirective>
        </TabComponent>

      </div>
    </div>
  );
};

export default CurrentSeason;