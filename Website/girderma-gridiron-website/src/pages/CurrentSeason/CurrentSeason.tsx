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
  { header: 'EarnedWins', Component: EarnedWins },
];

// ---------------------------------------------------------------------------
// Current Season
// ---------------------------------------------------------------------------

const CurrentSeason: React.FC = () => {
  return (
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ padding: '20px', width: '100%', maxWidth: '900px' }}>

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