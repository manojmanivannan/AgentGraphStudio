import { describe, expect, it } from "vitest";
import type { NodeChange } from "@xyflow/react";
import { withoutMeasurementChanges } from "./canvasNodeChanges";

describe("withoutMeasurementChanges", () => {
  it("drops dimensions changes (node measurement, not a user edit)", () => {
    const changes: NodeChange[] = [
      { type: "dimensions", id: "n1", dimensions: { width: 100, height: 40 } },
      { type: "position", id: "n1", position: { x: 12, y: 34 } },
      { type: "select", id: "n1", selected: true },
    ];

    expect(withoutMeasurementChanges(changes)).toEqual([
      { type: "position", id: "n1", position: { x: 12, y: 34 } },
      { type: "select", id: "n1", selected: true },
    ]);
  });

  it("returns an empty array when every change is a dimensions change", () => {
    const changes: NodeChange[] = [
      { type: "dimensions", id: "n1", dimensions: { width: 100, height: 40 } },
      { type: "dimensions", id: "n2", dimensions: { width: 80, height: 36 } },
    ];

    expect(withoutMeasurementChanges(changes)).toEqual([]);
  });

  it("keeps add, remove, and replace changes untouched", () => {
    const changes: NodeChange[] = [
      { type: "add", item: { id: "n1", position: { x: 0, y: 0 }, data: {} } },
      { type: "remove", id: "n1" },
      { type: "replace", id: "n1", item: { id: "n1", position: { x: 0, y: 0 }, data: {} } },
    ];

    expect(withoutMeasurementChanges(changes)).toEqual(changes);
  });
});
