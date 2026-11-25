import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

interface SimulatedRecordDistributionProps {
  year: number | string;
}

const SimulatedRecordDistribution: React.FC<SimulatedRecordDistributionProps> = ({ year }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);

  // Load the chart image for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);

    import(
      `../../../../league_stats_output/${year}/Simulations/record_distribution.png`
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
      title="Simulated Record Distribution"
      description="Simulated Record Distribution for rest of season"
      imageSrc={imageSrc}
      imageAlt="No chart available"
      fallbackText="No chart available."
    />
  );
};

export default SimulatedRecordDistribution;