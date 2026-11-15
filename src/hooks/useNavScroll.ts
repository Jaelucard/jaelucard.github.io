import { useEffect } from 'react';

/** Apply the navigation background once the page has scrolled. */
export function useNavScroll() {
  useEffect(() => {
    const nav = document.getElementById('nav');
    if (!nav) return;

    const updateNav = () => nav.classList.toggle('scrolled', window.scrollY > 24);
    updateNav();
    window.addEventListener('scroll', updateNav, { passive: true });
    return () => window.removeEventListener('scroll', updateNav);
  }, []);
}
