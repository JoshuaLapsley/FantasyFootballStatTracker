import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

interface TeamRankOverTimeProps {
  year: number | string;
}

const TeamRankOverTime: React.FC<TeamRankOverTimeProps> = ({ year }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);

  // Load the chart image for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);

    import(
      `../../../../league_stats_output/${year}/TeamRankOverTime/bump_chart_${year}.jpg`
    )
      .then((module) => {
        if (cancelled) return;
        setImageSrc(module.default as string);
      })
      .catch(() => {
        if (cancelled) return;
        setImageSrc(null);
      });

    return () => {
      cancelled = true;
    };
  }, [year]);

  return (
    <ImageCard
      title="Team Rank Over Time"
      description="Graph of teams over the course of the season."
      imageSrc={imageSrc}
      imageAlt="No chart available"
      fallbackText="No chart available."
    />
  );
};

export default TeamRankOverTime;