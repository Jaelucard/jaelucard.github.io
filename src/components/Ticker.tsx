const TICKER_ITEMS = [
  'Jarrod Low',
  'Based in Hangzhou',
  'Computer Science',
  'SUTD · ZJU',
] as const;

const GROUP_ITEMS = [...TICKER_ITEMS, ...TICKER_ITEMS, ...TICKER_ITEMS];

export function Ticker() {
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-track">
        <div className="ticker-group">
          {GROUP_ITEMS.map((item, index) => <span key={`a-${index}`}>{item}</span>)}
        </div>
        <div className="ticker-group">
          {GROUP_ITEMS.map((item, index) => <span key={`b-${index}`}>{item}</span>)}
        </div>
      </div>
    </div>
  );
}
