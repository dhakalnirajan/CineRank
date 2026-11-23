import type { CSSProperties } from "react";
import { cn } from "../../utils/cn";
import type { PosterShape, PosterShapeLayer, PosterShapeTone } from "./posterShapeMath";

const TONE_CLASS: Record<PosterShapeTone, string> = {
  ember: "text-accent",
  amber: "text-[#c2703a]",
  bone: "text-[#e7d9c2]",
  steel: "text-[#7f93a8]",
};

type ShapeStyle = CSSProperties & Record<`--shape-${string}`, string>;

function layerStyle(layer: PosterShapeLayer, intensity: number): ShapeStyle {
  const motion = layer.motion;
  return {
    left: `${layer.x}%`,
    top: `${layer.y}%`,
    width: `${layer.width}%`,
    // Keep overlaps translucent even on the fallback surface.
    opacity: Math.min(0.55, layer.opacity * intensity),
    transform: `translate(-50%, -50%) rotate(${layer.rotation}deg)`,
    filter: `blur(${motion.blur.toFixed(1)}px) drop-shadow(0 0 20px currentColor)`,
    mixBlendMode: "screen",
    animationName: "poster-shape-drift",
    animationDuration: `${motion.duration.toFixed(1)}s`,
    animationDelay: `-${motion.delay}s`,
    animationTimingFunction: "cubic-bezier(0.45, 0.05, 0.55, 0.95)",
    animationIterationCount: "infinite",
    animationDirection: "alternate",
    "--shape-rotation": `${layer.rotation}deg`,
    "--shape-tilt": `${motion.tilt}deg`,
    "--shape-drift-x": `${motion.driftX}%`,
    "--shape-drift-y": `${motion.driftY}%`,
    "--shape-scale": motion.scale.toFixed(3),
  };
}

interface PosterShapeArtProps {
  shape: PosterShape;
  className?: string;
  /**
   * Multiplies the layer opacity. Artwork needs a softer overlay than the
   * typographic fallback, so each surface can tune the same composition.
   */
  intensity?: number;
}

export function PosterShapeArt({ shape, className, intensity = 1 }: PosterShapeArtProps) {
  return (
    <span
      aria-hidden="true"
      className={cn("poster-shape-fluid pointer-events-none absolute inset-0", className)}
    >
      {shape.layers.map((layer, index) => (
        <span
          key={`${layer.sides}-${layer.points}-${index}`}
          className={cn("poster-shape-layer absolute block aspect-square", TONE_CLASS[layer.tone])}
          style={layerStyle(layer, intensity)}
        >
          <span
            className="poster-shape-enter block size-full"
            style={{ animationDelay: `${0.12 + index * 0.16}s` }}
          >
            <span
              className="poster-shape-morph block size-full"
              style={{
                animationDelay: `-${index * 2.3}s`,
                animationDuration: `${layer.motion.morphDuration.toFixed(1)}s`,
              }}
            >
              <svg
                viewBox="0 0 100 100"
                fill="currentColor"
                className="size-full"
                aria-hidden="true"
              >
                <polygon
                  points={layer.points}
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
          </span>
        </span>
      ))}
    </span>
  );
}
