import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

interface ProjectedTeamPointsProps {
  year: number | string;
}

const ProjectedTeamPoints: React.FC<ProjectedTeamPointsProps> = ({ year }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);

  // Load the chart image for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);

    import(
      `../../../../league_stats_output/${year}/Simulations/projected_team_points.png`
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
      title="Projected Team Points"
      description="Projected Team Points for rest of season (Sleeper Projections)"
      imageSrc={imageSrc}
      imageAlt="No chart available"
      fallbackText="No chart available."
    />
  );
};

export default ProjectedTeamPoints;