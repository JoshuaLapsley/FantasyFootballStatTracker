import React from 'react';
import ImageCard from '../Components/ImageCard';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/2026/Simulations/projected_team_points.png');
} catch {
  imageSrc = null;
}

const ProjectedTeamPoints: React.FC = () => (
  <ImageCard
    title="Projected Team Points"
    description="Projected Team Points for rest of season (Sleeper Projections)"
    imageSrc={imageSrc}
    imageAlt="No chart available"
    fallbackText="No chart available."
  />
);

export default ProjectedTeamPoints;