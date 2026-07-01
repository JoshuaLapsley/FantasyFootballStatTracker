import React, { useRef, useEffect, useState } from 'react';
import { TabComponent, TabItemsDirective, TabItemDirective, SelectEventArgs } from '@syncfusion/ej2-react-navigations';

// Required Syncfusion styles (adjust theme name if you use a different one)
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-buttons/styles/material.css';
import '@syncfusion/ej2-navigations/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';
import TeamRankOverTime from './TeamRankOverTime/TeamRankOverTime';
import Playoffs from './Playoffs/Playoffs';
import TradeData from './TradeData/TradeData';
import Rosters from './Rosters/Rosters';
import RegularSeason from './RegularSeason/RegularSeason';
import Draft from './Draft/TeamRankOverTime';

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

// Registry of second-level tabs. Order here = order shown in the UI.
const SUB_TABS: SubTabConfig[] = [
  { header: 'Team Rank over Time', Component: TeamRankOverTime },
  { header: 'Trade Data', Component: TradeData },
  { header: 'Playoffs', Component: Playoffs },
  { header: 'Rosters', Component: Rosters },
  { header: 'Regular Season', Component: RegularSeason },
  { header: 'Draft', Component: Draft },
];

// ---------------------------------------------------------------------------
// Second-level tab strip, rendered once per year.
//
// The active sub-tab index is passed down from the parent (RankDashboard)
// instead of being owned internally by each TabComponent. That's what lets
// the selection survive switching between year tabs: every YearContent
// instance is kept in sync with the same shared index.
// ---------------------------------------------------------------------------

interface YearContentProps {
  year: Year;
  activeSubTab: number;
  onSubTabChange: (index: number) => void;
}

const YearContent: React.FC<YearContentProps> = ({ year, activeSubTab, onSubTabChange }) => {
  const tabRef = useRef<TabComponent>(null);

  // Whenever the shared index changes (e.g. because you picked a different
  // sub-tab while on another year), push it into this TabComponent too.
  useEffect(() => {
    tabRef.current?.select(activeSubTab);
  }, [activeSubTab]);

  return (
    <TabComponent
      ref={tabRef}
      heightAdjustMode="Auto"
      selectedItem={activeSubTab}
      selected={(e: SelectEventArgs) => onSubTabChange(e.selectedIndex)}
    >
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
  const [activeSubTab, setActiveSubTab] = useState(0);

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
                content={() => (
                  <YearContent
                    year={year}
                    activeSubTab={activeSubTab}
                    onSubTabChange={setActiveSubTab}
                  />
                )}
              />
            ))}
          </TabItemsDirective>
        </TabComponent>
      </div>
    </div>
  );
};

export default RankDashboard;