import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

import './WARDraftBoard.css';

interface WARDraftBoardProps {
  year: number | string;
}

const WARDraftBoard: React.FC<WARDraftBoardProps> = ({ year }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [secondImageSrc, setSecondImageSrc] = useState<string | null>(null);

  // Load both images for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);
    setSecondImageSrc(null);

    import(
      `../../../../league_stats_output/${year}/War/draft_board_by_war_${year}.png`
    )
      .then((module) => {
        if (cancelled) return;
        setImageSrc(module.default as string);
      })
      .catch(() => {
        if (cancelled) return;
        setImageSrc(null);
      });

    import(
      `../../../../league_stats_output/${year}/War/draft_board_by_war_${year}_colorbar.png`
    )
      .then((module) => {
        if (cancelled) return;
        setSecondImageSrc(module.default as string);
      })
      .catch(() => {
        if (cancelled) return;
        setSecondImageSrc(null);
      });

    return () => {
      cancelled = true;
    };
  }, [year]);

  return (
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
};

export default WARDraftBoard;