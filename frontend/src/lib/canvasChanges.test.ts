import { describe, expect, it } from "vitest";
import type { EdgeChange, NodeChange } from "@xyflow/react";
import { hasSubstantiveChanges, withoutMeasurementChanges } from "./canvasChanges";

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

describe("hasSubstantiveChanges", () => {
  it("returns true for structural edits (add/remove/replace)", () => {
    expect(
      hasSubstantiveChanges([
        { type: "remove", id: "n1" },
      ])
    ).toBe(true);
    expect(
      hasSubstantiveChanges([
        { type: "add", item: { id: "n1", position: { x: 0, y: 0 }, data: {} } },
      ])
    ).toBe(true);
    expect(
      hasSubstantiveChanges([
        { type: "replace", id: "n1", item: { id: "n1", position: { x: 0, y: 0 }, data: {} } },
      ])
    ).toBe(true);
  });

  it("returns false for transient position and selection changes", () => {
    expect(
      hasSubstantiveChanges([
        { type: "position", id: "n1", position: { x: 12, y: 34 } },
      ])
    ).toBe(false);
    expect(
      hasSubstantiveChanges([
        { type: "select", id: "n1", selected: true },
      ])
    ).toBe(false);
  });

  it("returns true when a mixed batch contains any structural edit", () => {
    expect(
      hasSubstantiveChanges([
        { type: "position", id: "n1", position: { x: 12, y: 34 } },
        { type: "select", id: "n1", selected: true },
        { type: "remove", id: "n2" },
      ])
    ).toBe(true);
  });

  it("returns false for an empty change set", () => {
    expect(hasSubstantiveChanges([])).toBe(false);
  });

  it("returns false for edge selection changes", () => {
    const changes: EdgeChange[] = [
      { type: "select", id: "e1", selected: true },
    ];
    expect(hasSubstantiveChanges(changes)).toBe(false);
  });

  it("returns true for edge removal and replacement", () => {
    expect(
      hasSubstantiveChanges([{ type: "remove", id: "e1" }] as EdgeChange[])
    ).toBe(true);
    expect(
      hasSubstantiveChanges([
        { type: "replace", id: "e1", item: { id: "e1", source: "a", target: "b" } },
      ] as EdgeChange[])
    ).toBe(true);
  });
});
