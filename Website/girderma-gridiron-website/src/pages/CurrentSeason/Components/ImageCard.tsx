import React from 'react';
import './ImageCard.css';

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
  <article className="image-card">
    <div className="image-card__header">
      <h3>{title}</h3>
      {description && <p>{description}</p>}
    </div>

    {imageSrc ? (
      <div className="image-card__image-container">
        <img
          className="image-card__image"
          src={imageSrc}
          alt={imageAlt ?? title}
          loading="lazy"
        />
      </div>
    ) : (
      <p className="image-card__fallback">{fallbackText}</p>
    )}
  </article>
);

export default ImageCard;