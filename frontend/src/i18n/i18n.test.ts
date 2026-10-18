/* =========================================================
   I18N DICTIONARY PARITY

   The contract that makes the fallback honest: every
   English key has a Marathi value, every Marathi key has an
   English source, and neither table ships empty strings.
   A new key added to en.ts without its मराठी twin fails
   here rather than silently degrading at runtime.
   ========================================================= */

import { describe, expect, it } from "vitest";

import { en } from "./en";
import { mr } from "./mr";
import { MESSAGE_MAP } from "./messages";

describe("i18n dictionaries", () => {
  it("has a Marathi value for every English key", () => {
    const missing = Object.keys(en).filter((key) => !(key in mr));

    expect(missing).toEqual([]);
  });

  it("has no Marathi keys without an English source", () => {
    const extra = Object.keys(mr).filter((key) => !(key in en));

    expect(extra).toEqual([]);
  });

  it("ships no empty strings in either table", () => {
    const emptyEn = Object.keys(en).filter((key) => !en[key].trim());
    const emptyMr = Object.keys(mr).filter((key) => !mr[key].trim());

    expect(emptyEn).toEqual([]);
    expect(emptyMr).toEqual([]);
  });

  it("keeps every mapped message translated", () => {
    const empty = Object.entries(MESSAGE_MAP)
      .filter(([english, marathi]) => !english.trim() || !marathi.trim())
      .map(([english]) => english);

    expect(empty).toEqual([]);
  });
});
