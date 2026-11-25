import React, { useEffect, useState } from 'react';
import ImageCard from '../Components/ImageCard';

interface SimulatedConditionsProps {
  year: number | string;
}

const SimulatedConditions: React.FC<SimulatedConditionsProps> = ({ year }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);

  // Load the chart image for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);

    import(
      `../../../../league_stats_output/${year}/Simulations/conditional_outcomes_by_record.png`
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
      title="Simulated Conditions"
      description="Simulated Conditions for rest of season"
      imageSrc={imageSrc}
      imageAlt="No chart available"
      fallbackText="No chart available."
    />
  );
};

export default SimulatedConditions;