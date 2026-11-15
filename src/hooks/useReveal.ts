import { useEffect } from 'react';

/** Reveal page sections as they enter the viewport, respecting reduced motion. */
export function useReveal() {
  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>('.reveal');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reducedMotion || !('IntersectionObserver' in window)) {
      targets.forEach((target) => target.classList.add('in'));
      return;
    }

    // Keep pre-rendered content already on screen from disappearing at hydration.
    targets.forEach((target) => {
      const bounds = target.getBoundingClientRect();
      if (bounds.bottom > 0 && bounds.top < window.innerHeight) target.classList.add('in');
    });
    document.documentElement.classList.add('js-reveal');

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });

    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);
}
