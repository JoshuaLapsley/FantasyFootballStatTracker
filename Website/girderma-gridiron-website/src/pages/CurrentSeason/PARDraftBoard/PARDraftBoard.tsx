import React from 'react';
import ImageCard from '../Components/ImageCard';

import './PARDraftBoard.css';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/CurrentSeason/DraftBoards/PAR/draft_board_by_par_2026.png');
} catch {
  imageSrc = null;
}

let secondImageSrc: string | null = null;
try {
  secondImageSrc = require('../../../league_stats_output/CurrentSeason/DraftBoards/PAR/draft_board_by_par_2026_colorbar.png');
} catch {
  secondImageSrc = null;
}

const PARDraftBoard: React.FC = () => (
  <div className="draft-board-page">
    <ImageCard
      title="PAR Draft Board"
      description="PAR (Points Above Replacement) is the number of points a player has added to the team compared to what the best player available on waivers for that same position would give the team. It is a player-based metric that accounts for positional scarcity."
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