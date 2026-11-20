import type { Playback } from './playback';

export interface PollingOptions {
  activePollMs?: number;
  idlePollMs?: number;
}

const DEFAULT_ACTIVE_POLL_MS = 10_000;
const DEFAULT_IDLE_POLL_MS = 30_000;

/**
 * Poll without overlapping requests, pause while the page is hidden,
 * adapt cadence between active and idle states, and catch up on return.
 */
export function startPlaybackPolling(
  load: (signal: AbortSignal) => Promise<Playback | null>,
  onPlayback: (playback: Playback | null) => void,
  options: number | PollingOptions = {},
): () => void {
  const activePollMs = typeof options === 'number' ? options : (options.activePollMs ?? DEFAULT_ACTIVE_POLL_MS);
  const idlePollMs = typeof options === 'number' ? options : (options.idlePollMs ?? DEFAULT_IDLE_POLL_MS);

  let stopped = false;
  let inFlight = false;
  let queued = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;

  function isHidden() {
    return document.visibilityState === 'hidden';
  }

  function scheduleNext(result: Playback | null) {
    clearTimeout(timer);
    if (stopped || isHidden()) return;
    const delay = result?.status === 'playing' ? activePollMs : idlePollMs;
    timer = setTimeout(refresh, delay);
  }

  function refresh() {
    if (stopped || isHidden()) return;
    clearTimeout(timer);
    if (inFlight) {
      queued = true;
      return;
    }

    inFlight = true;
    controller = new AbortController();
    void (async () => {
      let result: Playback | null = null;
      try {
        result = await load(controller!.signal);
        if (!stopped) onPlayback(result);
      } catch {
        result = null;
        if (!stopped) onPlayback(null);
      } finally {
        inFlight = false;
        controller = undefined;
        if (!stopped && !isHidden()) {
          if (queued) {
            queued = false;
            refresh();
          } else {
            scheduleNext(result);
          }
        }
      }
    })();
  }

  function onVisibilityChange() {
    if (isHidden()) {
      clearTimeout(timer);
    } else {
      refresh();
    }
  }

  document.addEventListener('visibilitychange', onVisibilityChange);
  window.addEventListener('pageshow', refresh);
  if (!isHidden()) refresh();

  return () => {
    stopped = true;
    clearTimeout(timer);
    controller?.abort();
    document.removeEventListener('visibilitychange', onVisibilityChange);
    window.removeEventListener('pageshow', refresh);
  };
}
