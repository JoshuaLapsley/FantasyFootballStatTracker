import React from 'react';
import ImageCard from '../Components/ImageCard';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/CurrentSeason/DraftBoards/WAR/draft_board_by_war_2026.png');
} catch {
  imageSrc = null;
}

let secondImageSrc: string | null = null;
try {
  secondImageSrc = require('../../../league_stats_output/CurrentSeason/DraftBoards/WAR/draft_board_by_war_2026_colorbar.png');
} catch {
  secondImageSrc = null;
}

const WARDraftBoard: React.FC = () => (
  <>
    <ImageCard
      title="WAR Draft Board"
      description="WAR (Wins Above Replacement) is the number of wins a player adds to an average team compared to the best player available on waivers for that same position. It is the increase in win probability that the player would have given to an average team facing an average opponent, compared to if they started the waiver wire player in place. It is different from PAR in that a player who performs more consistently is worth more than a player with a higher weekly variance (this comes from the S-shaped curve of the CDF function). Note also that WAR is league-season specific, as it depends on the average performance of each fantasy team. Levi believes that WAR is the best all-in-one metric for measuring a player’s fantasy performance."
      imageSrc={imageSrc}
      imageAlt="WAR draft board"
      fallbackText="No chart available."
    />
    {secondImageSrc && (
      <img
        src={secondImageSrc}
        alt="Second chart"
        style={{ maxWidth: '100%', height: 'auto', padding: '0 20px' }}
      />
    )}
  </>
);

export default WARDraftBoard;