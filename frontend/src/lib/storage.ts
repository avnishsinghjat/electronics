/** localStorage wrappers for per-viewer conveniences; never throw (private mode etc.). */
export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(`fabtrack.${key}`);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(`fabtrack.${key}`, value);
  } catch {
    /* storage unavailable: the preference simply is not remembered */
  }
}
