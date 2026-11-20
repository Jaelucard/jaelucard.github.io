import { RadioQuote } from '../features/radio-quotes/RadioQuote';

export function Hero({ quoteIndex, preview = false }: { quoteIndex?: number; preview?: boolean }) {
  return (
    <header className="hero" id={preview ? undefined : 'top'}>
      <div className={preview ? 'poster' : 'poster reveal'}>
        <p className="eyebrow poster-eyebrow">AI Engineer · Systems Builder</p>

        <h1 className="poster-title display">JARROD</h1>

        <div className="cells" aria-label="Quick stats and F1 radio quote">
          <div className="cell">
            <span className="cell-label">Seasons</span>
            <span className="cell-value">23</span>
          </div>
          <div className="cell">
            <span className="cell-label">Current Circuit</span>
            <span className="cell-value">Hangzhou</span>
          </div>
          <RadioQuote fixedIndex={quoteIndex} />
        </div>

        <p className="poster-desc">
          Computer Science and Design student at SUTD.
          I train vision models, stress-test language models,
          and build the systems around them.
        </p>
      </div>

      {!preview && <a className="hero-scroll mono" href="#projects">Scroll — lights out ↓</a>}
    </header>
  );
}
