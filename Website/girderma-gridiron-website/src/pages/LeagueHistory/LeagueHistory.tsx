import React from 'react';
import { TabComponent, TabItemsDirective, TabItemDirective } from '@syncfusion/ej2-react-navigations';

// Required Syncfusion styles (adjust theme name if you use a different one)
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-buttons/styles/material.css';
import '@syncfusion/ej2-navigations/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';
import TeamRankOverTime from './TeamRankOverTime/TeamRankOverTime';
import Playoffs from './Playoffs/Playoffs';
import TradeData from './TradeData/TradeData';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Year = '2023' | '2024' | '2025';

export interface SubTabContentProps {
  year: Year;
}

export interface SubTabConfig {
  header: string;
  Component: React.ComponentType<SubTabContentProps>;
}

// ---------------------------------------------------------------------------
// Sub-tab content components.
// Add a new component here + a new entry in SUB_TABS below to add more
// second-level tabs.
// ---------------------------------------------------------------------------







// Registry of second-level tabs. Order here = order shown in the UI.
const SUB_TABS: SubTabConfig[] = [
  { header: 'Team Rank over Time', Component: TeamRankOverTime },
  { header: 'Trade Data', Component: TradeData },
  { header: 'Playoffs', Component: Playoffs },
];

// ---------------------------------------------------------------------------
// Second-level tab strip, rendered once per year
// ---------------------------------------------------------------------------

const YearContent: React.FC<{ year: Year }> = ({ year }) => {
  return (
    <TabComponent heightAdjustMode="Auto">
      <TabItemsDirective>
        {SUB_TABS.map(({ header, Component }) => (
          <TabItemDirective
            key={header}
            header={{ text: header }}
            content={() => <Component year={year} />}
          />
        ))}
      </TabItemsDirective>
    </TabComponent>
  );
};

// ---------------------------------------------------------------------------
// Top-level year tabs
// ---------------------------------------------------------------------------

const YEARS: Year[] = ['2023', '2024', '2025'];

const RankDashboard: React.FC = () => {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
      }}
    >
      <div style={{ padding: '20px', width: '100%', maxWidth: '900px' }}>
        <h2 style={{ textAlign: 'center' }}>League History</h2>
        <TabComponent heightAdjustMode="Auto">
          <TabItemsDirective>
            {YEARS.map((year) => (
              <TabItemDirective
                key={year}
                header={{ text: year }}
                content={() => <YearContent year={year} />}
              />
            ))}
          </TabItemsDirective>
        </TabComponent>
      </div>
    </div>
  );
};

export default RankDashboard;