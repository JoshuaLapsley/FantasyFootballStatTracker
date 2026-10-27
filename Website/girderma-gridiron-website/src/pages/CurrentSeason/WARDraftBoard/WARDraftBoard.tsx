import React from 'react';
import ImageCard from '../Components/ImageCard';

import './WARDraftBoard.css';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/2026/War/draft_board_by_war_2026.png');
} catch {
  imageSrc = null;
}

let secondImageSrc: string | null = null;
try {
  secondImageSrc = require('../../../league_stats_output/2026/War/draft_board_by_war_2026_colorbar.png');
} catch {
  secondImageSrc = null;
}

const WARDraftBoard: React.FC = () => (
  <div className="draft-board-page">
    <ImageCard
      title="WAR Draft Board"
      description="WAR (Wins Above Replacement) is the number of wins a player adds to an average team compared to the best player available on waivers for that same position. It measures the increase in win probability compared to starting the waiver wire player instead. WAR also accounts for consistency: a player who performs consistently can be more valuable than one with higher weekly variance. WAR is league-season specific because it depends on the average performance of each fantasy team."
      imageSrc={imageSrc}
      imageAlt="WAR draft board"
      fallbackText="No chart available."
    />

    {secondImageSrc && (
      <div className="draft-board-page__colorbar">
        <img
          src={secondImageSrc}
          alt="WAR draft board color scale"
        />
      </div>
    )}
  </div>
);

export default WARDraftBoard;