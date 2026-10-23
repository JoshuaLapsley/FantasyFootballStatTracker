import React from 'react';
import ImageCard from '../Components/ImageCard';

let imageSrc: string | null = null;
try {
  imageSrc = require('../../../league_stats_output/CurrentSeason/Simulations/record_distribution.jpg');
} catch {
  imageSrc = null;
}

const SimulatedRecordDistribution: React.FC = () => (
  <ImageCard
    title="Simulated Record Distribution"
    description="Simulated Record Distribution for rest of season"
    imageSrc={imageSrc}
    imageAlt="No chart available"
    fallbackText="No chart available."
  />
);

export default SimulatedRecordDistribution;