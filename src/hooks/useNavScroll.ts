import { useEffect, useState } from 'react';

const SECTION_IDS = ['projects', 'skills', 'experience', 'marina-bay', 'contact'] as const;

export type NavSectionId = (typeof SECTION_IDS)[number];

/** Track navigation background state and the section currently in view. */
export function useNavScroll() {
  const [scrolled, setScrolled] = useState(false);
  const [activeSection, setActiveSection] = useState<NavSectionId | null>(null);

  useEffect(() => {
    let rafId = 0;

    function measure() {
      rafId = 0;
      setScrolled(window.scrollY > 24);

      const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 24;
      if (nearBottom) {
        setActiveSection('contact');
        return;
      }

      const threshold = Math.min(180, window.innerHeight * 0.28);
      let current: NavSectionId | null = null;
      for (const id of SECTION_IDS) {
        const el = document.getElementById(id);
        if (!el) continue;
        if (el.getBoundingClientRect().top <= threshold) current = id;
      }
      setActiveSection(current);
    }

    function schedule() {
      if (!rafId) rafId = requestAnimationFrame(measure);
    }

    measure();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule, { passive: true });
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
    };
  }, []);

  return { scrolled, activeSection };
}
