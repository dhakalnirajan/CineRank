import { describe, expect, it } from "vitest";
import { posterShape } from "../src/components/media/posterShapeMath";
import type { PosterShapeLayer } from "../src/components/media/posterShapeMath";

function signature(seed: string): string {
  const shape = posterShape(seed);
  const layer = (value: PosterShapeLayer) =>
    [
      value.sides,
      value.points,
      value.tone,
      value.x,
      value.y,
      value.width,
      value.rotation,
      value.opacity,
      value.motion.driftX,
      value.motion.driftY,
      value.motion.duration,
      value.motion.morphDuration,
    ].join(":");
  return shape.layers.map(layer).join("|");
}

function vertices(layer: PosterShapeLayer): Array<[number, number]> {
  return layer.points.split(" ").map((point) => {
    const [x, y] = point.split(",").map(Number);
    return [x ?? 0, y ?? 0];
  });
}

function sideLengths(layer: PosterShapeLayer): number[] {
  const points = vertices(layer);
  return points.map(([x, y], index) => {
    const [nextX, nextY] = points[(index + 1) % points.length] ?? [0, 0];
    return Math.hypot(nextX - x, nextY - y);
  });
}

describe("posterShape", () => {
  it("is stable for the same title", () => {
    expect(posterShape("The Matrix|1999")).toEqual(posterShape("  the matrix|1999  "));
  });

  it("keeps shape, position and rotation distinct across a catalogue sample", () => {
    const titles = Array.from({ length: 600 }, (_, index) => `Film Number ${index}|${1950 + (index % 70)}`);
    const signatures = new Set(titles.map(signature));
    expect(signatures.size).toBe(titles.length);
  });

  it("generates between three and ten sides with unequal side lengths", () => {
    for (let index = 0; index < 150; index += 1) {
      for (const layer of posterShape(`Polygon Sample ${index}|2001`).layers) {
        expect(layer.sides).toBeGreaterThanOrEqual(3);
        expect(layer.sides).toBeLessThanOrEqual(10);
        expect(vertices(layer)).toHaveLength(layer.sides);
        const lengths = sideLengths(layer);
        expect(new Set(lengths.map((value) => value.toFixed(2))).size).toBeGreaterThan(1);
      }
    }
  });

  it("keeps every layer inside the cover and within visual bounds", () => {
    for (let index = 0; index < 200; index += 1) {
      const shape = posterShape(`Sample Title ${index}|2001`);
      expect(shape.layers).toHaveLength(4);
      for (const layer of shape.layers) {
        expect(layer.x).toBeGreaterThanOrEqual(15);
        expect(layer.x).toBeLessThanOrEqual(85);
        expect(layer.y).toBeGreaterThanOrEqual(15);
        expect(layer.y).toBeLessThanOrEqual(85);
        expect(layer.width).toBeGreaterThan(0);
        expect(layer.opacity).toBeGreaterThan(0);
        expect(layer.opacity).toBeLessThanOrEqual(0.3);
        expect(layer.rotation).toBeGreaterThanOrEqual(0);
        expect(layer.rotation).toBeLessThan(360);
        for (const [x, y] of vertices(layer)) {
          expect(x).toBeGreaterThanOrEqual(0);
          expect(x).toBeLessThanOrEqual(100);
          expect(y).toBeGreaterThanOrEqual(0);
          expect(y).toBeLessThanOrEqual(100);
        }
      }
    }
  });
});
