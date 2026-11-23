export const POSTER_SHAPE_TONES = ["ember", "amber", "bone", "steel"] as const;

export type PosterShapeTone = (typeof POSTER_SHAPE_TONES)[number];

export interface PosterShapeMotion {
  /** Drift distance as a percentage of the layer width. */
  driftX: number;
  driftY: number;
  /** Extra rotation added at the far end of the cycle. */
  tilt: number;
  duration: number;
  delay: number;
  scale: number;
  blur: number;
  /** Slow inner rotation and skew that keeps the silhouette fluid. */
  morphDuration: number;
}

export interface PosterShapeLayer {
  /** Number of polygon sides, from 3 to 10 inclusive. */
  sides: number;
  /** SVG polygon points in a 100 x 100 view box. */
  points: string;
  tone: PosterShapeTone;
  /** Horizontal center as a percentage of the cover width. */
  x: number;
  /** Vertical center as a percentage of the cover height. */
  y: number;
  /** Layer width as a percentage of the cover width. */
  width: number;
  rotation: number;
  opacity: number;
  motion: PosterShapeMotion;
}

export interface PosterShape {
  layers: PosterShapeLayer[];
}

const HASH_OFFSET = 0x811c9dc5;
const HASH_PRIME = 0x01000193;
const MAX_SIDES = 10;

interface LayerOptions {
  salt: number;
  minimumWidth: number;
  maximumWidth: number;
  minimumOpacity: number;
  maximumOpacity: number;
  minimumDrift: number;
  maximumDrift: number;
  minimumDuration: number;
  maximumDuration: number;
  minimumBlur: number;
  maximumBlur: number;
}

const LAYERS: readonly Omit<LayerOptions, "salt">[] = [
  {
    minimumWidth: 46,
    maximumWidth: 76,
    minimumOpacity: 16,
    maximumOpacity: 30,
    minimumDrift: 14,
    maximumDrift: 26,
    minimumDuration: 8,
    maximumDuration: 15,
    minimumBlur: 2.4,
    maximumBlur: 6.5,
  },
  {
    minimumWidth: 20,
    maximumWidth: 38,
    minimumOpacity: 12,
    maximumOpacity: 24,
    minimumDrift: 20,
    maximumDrift: 32,
    minimumDuration: 7,
    maximumDuration: 13,
    minimumBlur: 1.6,
    maximumBlur: 4.5,
  },
  {
    minimumWidth: 34,
    maximumWidth: 58,
    minimumOpacity: 9,
    maximumOpacity: 18,
    minimumDrift: 16,
    maximumDrift: 30,
    minimumDuration: 9,
    maximumDuration: 16,
    minimumBlur: 2.8,
    maximumBlur: 7.5,
  },
  {
    minimumWidth: 10,
    maximumWidth: 24,
    minimumOpacity: 14,
    maximumOpacity: 26,
    minimumDrift: 22,
    maximumDrift: 36,
    minimumDuration: 6,
    maximumDuration: 12,
    minimumBlur: 1.2,
    maximumBlur: 3.5,
  },
];

const LAYER_SALTS = [
  0x27d4eb2f,
  0x165667b1,
  0x9e3779b1,
  0x85ebca77,
] as const;

/**
 * Deterministic 32-bit FNV-1a hash with a murmur3-style avalanche step.
 *
 * The title is folded character by character, so titles that differ by a
 * single letter still produce unrelated bit patterns after mixing. Separate
 * salts give each layer roughly independent shape, position, tone and motion.
 */
function hashText(text: string, salt: number): number {
  let hash = (HASH_OFFSET ^ salt) >>> 0;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, HASH_PRIME) >>> 0;
  }
  hash ^= hash >>> 16;
  hash = Math.imul(hash, 0x7feb352d) >>> 0;
  hash ^= hash >>> 15;
  hash = Math.imul(hash, 0x846ca68b) >>> 0;
  hash ^= hash >>> 16;
  return hash >>> 0;
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 0x100000000;
  };
}

function pick<T>(values: readonly T[], value: number): T {
  return values[value % values.length] as T;
}

function numberInRange(value: number, minimum: number, maximum: number): number {
  return minimum + (value % (maximum - minimum + 1));
}

/**
 * Build an irregular polygon. The side count is 3 to 10, vertices are spaced
 * around the center with a small angular jitter, and every vertex gets a
 * different radius so no two sides share a length.
 */
function buildPolygon(seed: number): { sides: number; points: string } {
  const random = mulberry32(seed);
  const sides = 3 + Math.floor(random() * (MAX_SIDES - 2));
  const step = (Math.PI * 2) / sides;
  const start = random() * Math.PI * 2;
  const vertices: string[] = [];

  for (let index = 0; index < sides; index += 1) {
    // Keep the jitter below half a step so vertex order never crosses over.
    const angle = start + index * step + (random() - 0.5) * step * 0.72;
    const radius = 24 + random() * 22;
    const x = 50 + Math.cos(angle) * radius;
    const y = 50 + Math.sin(angle) * radius;
    vertices.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }

  return { sides, points: vertices.join(" ") };
}

function buildLayer(key: string, index: number, options: LayerOptions): PosterShapeLayer {
  const variationHash = hashText(`${key}|layer:${index}`, options.salt);
  const positionHash = hashText(`${key}|position:${index}`, options.salt ^ 0x85ebca6b);
  const polygonHash = hashText(`${key}|polygon:${index}`, options.salt ^ 0xc2b2ae35);
  const motionHash = hashText(`${key}|motion:${index}`, options.salt ^ 0x27d4eb2f);
  const polygon = buildPolygon(polygonHash);

  return {
    sides: polygon.sides,
    points: polygon.points,
    tone: pick(POSTER_SHAPE_TONES, variationHash),
    x: numberInRange(positionHash, 15, 85),
    y: numberInRange(positionHash >>> 8, 15, 85),
    width: numberInRange(variationHash >>> 5, options.minimumWidth, options.maximumWidth),
    rotation: numberInRange(variationHash >>> 12, 0, 359),
    opacity:
      numberInRange(variationHash >>> 9, options.minimumOpacity, options.maximumOpacity) / 100,
    motion: {
      driftX: numberInRange(motionHash, options.minimumDrift, options.maximumDrift),
      driftY: numberInRange(motionHash >>> 4, options.minimumDrift, options.maximumDrift),
      tilt: numberInRange(motionHash >>> 9, 18, 44),
      // Fast, offset cycles make the layers visibly cross and separate.
      duration:
        numberInRange(motionHash >>> 13, options.minimumDuration, options.maximumDuration) +
        numberInRange(variationHash >>> 18, 0, 9) / 10,
      delay: numberInRange(motionHash >>> 17, 0, 14),
      scale: 1 + numberInRange(variationHash >>> 21, 8, 22) / 100,
      blur:
        options.minimumBlur +
        numberInRange(variationHash >>> 23, 0, Math.round((options.maximumBlur - options.minimumBlur) * 10)) / 10,
      morphDuration:
        numberInRange(motionHash >>> 19, 9, 17) +
        numberInRange(polygonHash >>> 7, 0, 9) / 10,
    },
  };
}

/**
 * Turn a movie title into a stable, layered shape composition.
 *
 * The seed is normalized so casing and stray spacing cannot change the art.
 * Release years are appended by the caller when known, which keeps remakes
 * with identical titles visually distinct.
 */
export function posterShape(seed: string): PosterShape {
  const key = seed.trim().toLowerCase().replace(/\s+/g, " ");

  return {
    layers: LAYERS.map((options, index) =>
      buildLayer(key, index, {
        ...options,
        salt: LAYER_SALTS[index] as number,
      }),
    ),
  };
}
