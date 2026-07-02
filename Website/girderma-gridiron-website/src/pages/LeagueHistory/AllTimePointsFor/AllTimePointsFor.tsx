

const AllTimePointsFor: React.FC = () => {

  let imageSrc: string | null = null;
  try {
    imageSrc = require(`../../../league_stats_output/bump_chart_points_for.jpeg`);
  } catch {
    imageSrc = null;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h3>All Time Wins</h3>
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={`All Time Points For`}
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      ) : (
        <p>No bump chart available.</p>
      )}
    </div>
  );
};

export default AllTimePointsFor;