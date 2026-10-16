import React from 'react';
import ImageCard from '../Components/ImageCard';

import './WARSurplus.css';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/CurrentSeason/DraftBoards/SurplusWar/draft_board_2026_surplus_war.png');
} catch {
  imageSrc = null;
}

let secondImageSrc: string | null = null;
try {
  secondImageSrc = require('../../../league_stats_output/CurrentSeason/DraftBoards/SurplusWar/draft_board_2026_surplus_war_colorbar.png');
} catch {
  secondImageSrc = null;
}

const PARDraftBoard: React.FC = () => (
  <div className="draft-board-page">
    <ImageCard
      title="Surplus WAR Draft Board"
      description="Surplus WAR, how much war a player adds to the team, above what the play is expected to produce where they are drafted."
      imageSrc={imageSrc}
      imageAlt="PAR draft board"
      fallbackText="No chart available."
    />

    {secondImageSrc && (
      <div className="draft-board-page__colorbar">
        <img
          src={secondImageSrc}
          alt="PAR draft board color scale"
        />
      </div>
    )}
  </div>
);

export default PARDraftBoard;