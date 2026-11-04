import { describe, expect, it } from "vitest";

import { formatBytes } from "@/features/system/format";

describe("formatBytes", () => {
  it.each([
    [null, "—"],
    [0, "0 B"],
    [1023, "1023 B"],
    [1024, "1.0 KiB"],
    [5 * 1024 ** 3, "5.0 GiB"],
    [3 * 1024 ** 5, "3072.0 TiB"],
  ])("%s -> %s", (input, expected) => {
    expect(formatBytes(input)).toBe(expected);
  });
});
