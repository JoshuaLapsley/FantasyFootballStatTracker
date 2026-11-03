import React from 'react';
import ImageCard from '../Components/ImageCard';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/2026/Simulations/conditional_outcomes_by_record.png');
} catch {
  imageSrc = null;
}

const SimulatedConditions: React.FC = () => (
  <ImageCard
    title="Simulated Conditions"
    description="Simulated Conditions for rest of season"
    imageSrc={imageSrc}
    imageAlt="No chart available"
    fallbackText="No chart available."
  />
);

export default SimulatedConditions;