import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

import './WARSurplus.css';

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
      `../../../../league_stats_output/${year}/SurplusWar/draft_board_surplus_war_${year}.png`
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
      `../../../../league_stats_output/${year}/SurplusWar/draft_board_surplus_war_${year}_colorbar.png`
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
};

export default PARDraftBoard;