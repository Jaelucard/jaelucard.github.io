import { inView } from 'motion';
import { useEffect } from 'react';

/** Reveal page sections as they enter the viewport, respecting reduced motion. */
export function useReveal() {
  useEffect(() => {
    const targets = Array.from(document.querySelectorAll<HTMLElement>('.reveal'));
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

    return inView(targets, (target) => {
      target.classList.add('in');
    }, { amount: 0.01, margin: '0px 0px -32px 0px' });
  }, []);
}
