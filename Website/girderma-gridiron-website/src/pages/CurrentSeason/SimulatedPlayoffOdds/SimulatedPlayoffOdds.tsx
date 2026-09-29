import React from 'react';
import ImageCard from '../Components/ImageCard';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/CurrentSeason/Simulations/playoff_odds.jpg');
} catch {
  imageSrc = null;
}

const SimulatedPlayoffOdds: React.FC = () => (
  <ImageCard
    title="Simulated Playoff Odds"
    description="Simulated Playoff Odds for rest of season"
    imageSrc={imageSrc}
    imageAlt="No chart available"
    fallbackText="No chart available."
  />
);

export default SimulatedPlayoffOdds;