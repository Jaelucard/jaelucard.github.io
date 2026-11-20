import { useRef, useState } from 'react';
import '../components/classification.css';
import { Footer } from '../components/Footer';
import { Hero } from '../components/Hero';
import { Navigation } from '../components/Navigation';
import { Ticker } from '../components/Ticker';
import { ContactSection } from '../features/contact/ContactSection';
import { ExperienceSection } from '../features/experience/ExperienceSection';
import { ProjectsSection } from '../features/projects/ProjectsSection';
import { SkillsSection } from '../features/skills/SkillsSection';
import { SpotifySection } from '../features/spotify/SpotifySection';
import { MarinaBaySection } from '../features/marina-bay/MarinaBaySection';
import { useNavScroll } from '../hooks/useNavScroll';
import { useReveal } from '../hooks/useReveal';
import { DetailPanel, type Selection } from '../components/DetailPanel';

export function App() {
  useNavScroll();
  useReveal();
  const [selection, setSelection] = useState<Selection | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  function openDetail(next: Selection, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setSelection(next);
  }

  return (
    <>
      <Navigation />
      <Hero />
      <Ticker />
      <SpotifySection />
      <MarinaBaySection />
      <ProjectsSection onOpen={openDetail} selected={selection} />
      <SkillsSection />
      <ExperienceSection onOpen={openDetail} selected={selection} />
      <ContactSection />
      <Footer />
      {selection && <DetailPanel selection={selection} trigger={triggerRef.current} onDismiss={() => setSelection(null)} />}
    </>
  );
}
