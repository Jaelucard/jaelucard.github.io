export function Footer({ onReplayIntro }: { onReplayIntro: () => void }) {
  return (
    <footer className="footer">
      <div className="wrap footer-grid">
        <span className="nav-brand">JAR<em>ROD</em></span>
        <ul className="footer-links">
          <li><a href="https://github.com/Jaelucard" target="_blank" rel="noopener noreferrer">GitHub</a></li>
          <li><a href="https://www.linkedin.com/in/jarrod-low/" target="_blank" rel="noopener noreferrer">LinkedIn</a></li>
          <li><a href="mailto:workjarrodlow@gmail.com">Email</a></li>
          <li className="footer-replay"><button type="button" onClick={onReplayIntro}>Replay intro <span aria-hidden="true">↻</span></button></li>
        </ul>
        <span className="mono">30.3050° N · 120.0921° E — EST. 2026</span>
      </div>
    </footer>
  );
}
