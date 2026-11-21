import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// jsdom has no object URLs; record them so tests can check create/revoke.
let counter = 0;
beforeEach(() => {
  URL.createObjectURL = vi.fn(() => `blob:fake-${++counter}`);
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});
