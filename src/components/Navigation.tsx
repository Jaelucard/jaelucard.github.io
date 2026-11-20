import { useEffect, useRef, useState } from 'react';
import { useNavScroll, type NavSectionId } from '../hooks/useNavScroll';

const NAV_ITEMS: readonly { id: NavSectionId; label: string }[] = [
  { id: 'projects', label: 'Projects' },
  { id: 'skills', label: 'Skills' },
  { id: 'experience', label: 'Experience' },
  { id: 'marina-bay', label: 'Play' },
];

export function Navigation() {
  const { scrolled, activeSection } = useNavScroll();
  const [menuOpen, setMenuOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!menuOpen) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false);
    }
    function onPointerDown(event: PointerEvent) {
      if (!navRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    function onResize() {
      if (window.innerWidth > 640) setMenuOpen(false);
    }

    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('resize', onResize);
    };
  }, [menuOpen]);

  return (
    <nav
      ref={navRef}
      className={`nav${scrolled ? ' scrolled' : ''}${menuOpen ? ' nav-open' : ''}`}
      id="nav"
      aria-label="Primary"
    >
      <a className="nav-brand" href="#top" onClick={() => setMenuOpen(false)}>JAR<em>ROD</em></a>
      <div className="nav-controls">
        <ul className="nav-links" id="nav-menu">
          {NAV_ITEMS.map(({ id, label }) => (
            <li key={id}>
              <a
                href={`#${id}`}
                aria-current={activeSection === id ? 'location' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                {label}
              </a>
            </li>
          ))}
          <li className="nav-cta-desktop">
            <a
              className="nav-cta"
              href="#contact"
              aria-current={activeSection === 'contact' ? 'location' : undefined}
              onClick={() => setMenuOpen(false)}
            >
              Contact
            </a>
          </li>
        </ul>
        <a
          className="nav-cta nav-cta-mobile"
          href="#contact"
          aria-current={activeSection === 'contact' ? 'location' : undefined}
          onClick={() => setMenuOpen(false)}
        >
          Contact
        </a>
        <button
          type="button"
          className="nav-toggle"
          aria-expanded={menuOpen}
          aria-controls="nav-menu"
          aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span>{menuOpen ? 'Close' : 'Menu'}</span>
        </button>
      </div>
    </nav>
  );
}
