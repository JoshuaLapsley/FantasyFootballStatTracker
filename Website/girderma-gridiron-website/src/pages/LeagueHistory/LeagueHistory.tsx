import React, { useRef, useEffect } from 'react';
import { useState } from 'react';
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
//
// NOTE: We only stop touch propagation on the tab *header* strip (the row
// of clickable tab labels), not on the whole content wrapper. Scoping it
// this way stops a horizontal swipe on the sub-tab labels from also
// dragging the outer year TabComponent, without blocking vertical
// scrolling anywhere else on the page (which is what happens if you slap
// `touchAction: 'pan-x'` + stopPropagation on a wrapper around everything).
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

  // Scope touch handling to just the Syncfusion tab header element so
  // swipes on the tab labels don't bubble to the outer year tabs, while
  // leaving vertical scroll on the actual tab content untouched.
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
        <TabComponent heightAdjustMode="Auto" overflowMode="Scrollable">
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
