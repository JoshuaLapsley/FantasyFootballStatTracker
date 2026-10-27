import React from 'react';
import ImageCard from '../Components/ImageCard';

import './WaiverWAR.css';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/2026/WaiverWar/waiver_war_board_2026.png');
} catch {
  imageSrc = null;
}

let secondImageSrc: string | null = null;
try {
  secondImageSrc = require('../../../league_stats_output/2026/WaiverWar/waiver_war_board_2026_colorbar.png');
} catch {
  secondImageSrc = null;
}

const PARDraftBoard: React.FC = () => (
  <div className="draft-board-page">
    <ImageCard
      title="Waiver WAR"
      description="WAR for all waiver players."
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