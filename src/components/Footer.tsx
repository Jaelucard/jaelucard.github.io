import { useEffect, useState } from 'react';

export function Footer() {
  const [year, setYear] = useState('');
  useEffect(() => setYear(String(new Date().getFullYear())), []);

  return (
    <footer className="footer">
      <div className="wrap footer-grid">
        <span className="nav-brand">JAR<em>ROD</em></span>
        <ul className="footer-links">
          <li><a href="https://github.com/Jaelucard" target="_blank" rel="noopener noreferrer">GitHub</a></li>
          <li><a href="https://www.linkedin.com/in/jarrod-low/" target="_blank" rel="noopener noreferrer">LinkedIn</a></li>
          <li><a href="mailto:workjarrodlow@gmail.com">Email</a></li>
        </ul>
        <span className="mono">30.3050° N · 120.0921° E — EST. <span id="year">{year}</span></span>
      </div>
    </footer>
  );
}
