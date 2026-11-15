import type { Playback } from './playback';

/** Poll without overlapping requests, and catch up when the page returns. */
export function startPlaybackPolling(
  load: (signal: AbortSignal) => Promise<Playback | null>,
  onPlayback: (playback: Playback | null) => void,
  pollMs = 5_000,
): () => void {
  let stopped = false;
  let inFlight = false;
  let queued = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;

  function refresh() {
    if (stopped) return;
    clearTimeout(timer);
    if (inFlight) {
      queued = true;
      return;
    }

    inFlight = true;
    controller = new AbortController();
    void (async () => {
      try {
        const result = await load(controller!.signal);
        if (!stopped) onPlayback(result);
      } catch {
        if (!stopped) onPlayback(null);
      } finally {
        inFlight = false;
        controller = undefined;
        if (!stopped) {
          if (queued) {
            queued = false;
            refresh();
          } else {
            timer = setTimeout(refresh, pollMs);
          }
        }
      }
    })();
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'visible') refresh();
  }

  document.addEventListener('visibilitychange', onVisibilityChange);
  window.addEventListener('pageshow', refresh);
  refresh();

  return () => {
    stopped = true;
    clearTimeout(timer);
    controller?.abort();
    document.removeEventListener('visibilitychange', onVisibilityChange);
    window.removeEventListener('pageshow', refresh);
  };
}
