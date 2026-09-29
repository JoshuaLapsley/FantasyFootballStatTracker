import React from 'react';

interface ImageCardProps {
  title: string;
  description?: string;
  imageSrc?: string | null;
  imageAlt?: string;
  fallbackText?: string;
}

const ImageCard: React.FC<ImageCardProps> = ({
  title,
  description,
  imageSrc,
  imageAlt,
  fallbackText = 'No image available.',
}) => (
  <div style={{ padding: '20px' }}>
    <h3>{title}</h3>
    {description && <p>{description}</p>}
    {imageSrc ? (
      <img
        src={imageSrc}
        alt={imageAlt ?? title}
        style={{ maxWidth: '100%', height: 'auto' }}
      />
    ) : (
      <p>{fallbackText}</p>
    )}
  </div>
);

export default ImageCard;