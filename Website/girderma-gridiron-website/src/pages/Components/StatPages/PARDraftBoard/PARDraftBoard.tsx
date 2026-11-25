import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

import './PARDraftBoard.css';

interface PARDraftBoardProps {
  year: number | string;
}

const PARDraftBoard: React.FC<PARDraftBoardProps> = ({ year }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [secondImageSrc, setSecondImageSrc] = useState<string | null>(null);

  // Load both images for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);
    setSecondImageSrc(null);

    import(
      `../../../../league_stats_output/${year}/Par/draft_board_by_par_${year}.png`
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
      `../../../../league_stats_output/${year}/Par/draft_board_by_par_${year}_colorbar.png`
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
};

export default PARDraftBoard;