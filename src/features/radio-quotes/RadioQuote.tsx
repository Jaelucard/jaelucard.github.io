import { useEffect, useState } from 'react';
import { radioQuotes } from './quotes';
import { dailyIndex, nextSingaporeMidnight } from './schedule';

export function RadioQuote() {
  // The static HTML and first browser render match, even across midnight.
  const [index, setIndex] = useState<number | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    function refresh() {
      clearTimeout(timer);
      const now = Date.now();
      setIndex(dailyIndex(now, radioQuotes.length));
      timer = setTimeout(refresh, nextSingaporeMidnight(now) - now);
    }

    function onVisibilityChange() {
      if (document.visibilityState === 'visible') refresh();
    }

    refresh();
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pageshow', refresh);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pageshow', refresh);
    };
  }, []);

  const quote = index === null ? null : radioQuotes[index];

  return (
    <div className="cell radio-quote-cell" aria-live="polite">
      <span className="cell-label">Team Radio</span>
      {quote ? (
        <>
          <span
            className={`cell-value radio-quote${'preserveCase' in quote && quote.preserveCase ? ' radio-quote-case-sensitive' : ''}`}
            aria-label={`F1 radio quote: ${quote.text}, ${quote.speaker}`}
          >
            “{quote.text}”
          </span>
          <span className="radio-speaker mono">— {quote.speaker}</span>
        </>
      ) : (
        <span className="cell-value radio-quote radio-quote-placeholder" aria-hidden="true">&nbsp;</span>
      )}
    </div>
  );
}
