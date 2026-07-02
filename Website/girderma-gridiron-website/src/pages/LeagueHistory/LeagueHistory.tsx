import React, { useRef, useEffect, useState } from 'react';
import { TabComponent, TabItemsDirective, TabItemDirective, SelectEventArgs } from '@syncfusion/ej2-react-navigations';

// Required Syncfusion styles (adjust theme name if you use a different one)
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-buttons/styles/material.css';
import '@syncfusion/ej2-navigations/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';
import TeamRankOverTime from './TeamRankOverTime/TeamRankOverTime';
import Rosters from './Rosters/Rosters';
import RegularSeason from './RegularSeason/RegularSeason';
import AllTimeWins from './AllTimeWins/AllTimeWins';
import AllTimePointsFor from './AllTimePointsFor/AllTimePointsFor';
import AllTimePointsAgainst from './AllTimePointsAgainst/AllTimePointsAgainst';

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

const YEARS: Year[] = ['2023', '2024', '2025', 'All Time'];

const SUB_TABS_YEAR: SubTabConfig[] = [
  { header: 'Team Rank over Time', Component: TeamRankOverTime },
  { header: 'Rosters', Component: Rosters },
  { header: 'Regular Season', Component: RegularSeason },
];

const SUB_TABS_ALL_TIME: SubTabConfig[] = [
  { header: 'All Time Wins', Component: AllTimeWins },
  { header: 'All Time Points For', Component: AllTimePointsFor },
  { header: 'All Time Points Against', Component: AllTimePointsAgainst },
];

const getSubTabs = (year: Year): SubTabConfig[] =>
  year === 'All Time' ? SUB_TABS_ALL_TIME : SUB_TABS_YEAR;

// ---------------------------------------------------------------------------
// Sub-tabs for a single year
// ---------------------------------------------------------------------------

interface YearContentProps {
  year: Year;
  activeSubTab: number;
  onSubTabChange: (index: number) => void;
}

const YearContent: React.FC<YearContentProps> = ({ year, activeSubTab, onSubTabChange }) => {
  const tabRef = useRef<TabComponent>(null);
  const subTabs = getSubTabs(year);
  const clampedIndex = Math.min(activeSubTab, subTabs.length - 1);

  // Keep this tab set in sync when the shared sub-tab index changes
  // (e.g. the user picked a sub-tab while viewing a different year).
  useEffect(() => {
    tabRef.current?.select(clampedIndex);
  }, [clampedIndex]);

  // Prevent swipes on the sub-tab header from bubbling up to the
  // outer year tabs, without affecting vertical scroll in the content.
  useEffect(() => {
    const rootEl = (tabRef.current as any)?.element as HTMLElement | undefined;
    const headerEl = rootEl?.querySelector('.e-tab-header') as HTMLElement | null;
    if (!headerEl) return;

    const stopTouch = (e: TouchEvent) => e.stopPropagation();
    headerEl.style.touchAction = 'pan-x';
    headerEl.addEventListener('touchstart', stopTouch, { passive: true });
    headerEl.addEventListener('touchmove', stopTouch, { passive: true });

    return () => {
      headerEl.removeEventListener('touchstart', stopTouch);
      headerEl.removeEventListener('touchmove', stopTouch);
    };
  }, []);

  return (
    <TabComponent
      ref={tabRef}
      heightAdjustMode="Auto"
      overflowMode="Scrollable"
      swipeMode="None"
      selectedItem={clampedIndex}
      selected={(e: SelectEventArgs) => onSubTabChange(e.selectedIndex)}
    >
      <TabItemsDirective>
        {subTabs.map(({ header, Component }) => (
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

const RankDashboard: React.FC = () => {
  const [activeSubTab, setActiveSubTab] = useState(0);

  return (
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ padding: '20px', width: '100%', maxWidth: '900px' }}>
        <h2 style={{ textAlign: 'center' }}>League History</h2>
        <TabComponent heightAdjustMode="Auto" overflowMode="Scrollable" swipeMode="None">
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
