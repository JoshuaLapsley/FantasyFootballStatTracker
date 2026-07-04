import React, { Children, isValidElement, ReactNode } from 'react';
import {
  CarouselComponent,
  CarouselItemsDirective,
  CarouselItemDirective,
} from '@syncfusion/ej2-react-navigations';

// Don't forget the Syncfusion styles (pick a theme, e.g. tailwind3/material/bootstrap5):
// import '@syncfusion/ej2-base/styles/tailwind3.css';
// import '@syncfusion/ej2-buttons/styles/tailwind3.css';
// import '@syncfusion/ej2-navigations/styles/tailwind3.css';

type AnimationEffect = 'Slide' | 'Fade' | 'Custom' | 'None';

export interface PhotoSlideshowProps {
  children: ReactNode;
  interval?: number;
  autoPlay?: boolean;
  loop?: boolean;
  showIndicators?: boolean;
  showArrows?: boolean;
  animationEffect?: AnimationEffect;
  /** CSS aspect-ratio, e.g. "16 / 9" or "4 / 3". Keeps the slideshow proportional at any width. */
  aspectRatio?: string;
  /** Caps how tall the slideshow can get on large screens. */
  maxHeight?: string;
  width?: string;
  arrowColor?: string;
}

// Simple chevron icon so we control the color directly (no fighting Syncfusion's icon font color)
function ChevronButton({
  direction,
  color,
}: {
  direction: 'left' | 'right';
  color: string;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 36,
        height: 36,
        borderRadius: '50%',
        background: 'rgba(0, 0, 0, 0.35)',
        cursor: 'pointer',
      }}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {direction === 'left' ? (
          <polyline points="15 18 9 12 15 6" />
        ) : (
          <polyline points="9 18 15 12 9 6" />
        )}
      </svg>
    </div>
  );
}

/**
 * PhotoSlideshow
 * Drop any number of <img> tags in as children and this renders them
 * as a Syncfusion Carousel slideshow.
 *
 * Usage:
 *   <PhotoSlideshow interval={4000} arrowColor="red">
 *     <img src="/photo1.jpg" alt="Beach" />
 *     <img src="/photo2.jpg" alt="Mountains" />
 *     <img src="/photo3.jpg" alt="City" />
 *   </PhotoSlideshow>
 */
export default function PhotoSlideshow({
  children,
  interval = 3000,
  autoPlay = true,
  loop = true,
  showIndicators = true,
  showArrows = true,
  animationEffect = 'Slide',
  aspectRatio = '16 / 9',
  maxHeight = '600px',
  width = '100%',
  arrowColor = 'red',
}: PhotoSlideshowProps) {
  // Grab only the <img> children the user passed in (ignores anything else by mistake)
  const images = Children.toArray(children).filter(
    (child): child is React.ReactElement<React.ImgHTMLAttributes<HTMLImageElement>> =>
      isValidElement(child) && child.type === 'img'
  );

  if (images.length === 0) {
    return null;
  }

  return (
    <div
      style={{
        width,
        maxWidth: '100%',
        aspectRatio,
        maxHeight,
        margin: '0 auto',
      }}
    >
      <CarouselComponent
        autoPlay={autoPlay}
        interval={interval}
        loop={loop}
        showIndicators={showIndicators}
        buttonsVisibility={showArrows ? 'Visible' : 'Hidden'}
        animationEffect={animationEffect}
        height="100%"
        width="100%"
        previousButtonTemplate={() => (
          <ChevronButton direction="left" color={arrowColor} />
        )}
        nextButtonTemplate={() => (
          <ChevronButton direction="right" color={arrowColor} />
        )}
      >
        <CarouselItemsDirective>
          {images.map((img, index) => (
            <CarouselItemDirective
              key={img.key ?? index}
              template={() => (
                <div style={{ width: '100%', height: '100%' }}>
                  {React.cloneElement(img, {
                    style: {
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                      ...img.props.style,
                    },
                  })}
                </div>
              )}
            />
          ))}
        </CarouselItemsDirective>
      </CarouselComponent>
    </div>
  );
}
