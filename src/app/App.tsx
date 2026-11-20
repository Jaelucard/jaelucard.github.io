'use client';

import { useRef, useState } from 'react';
import '../components/classification.css';
import { INTRO_CONFIG, type IntroMedia } from '../config/intro';
import { DetailPanel } from '../components/DetailPanel';
import { Footer } from '../components/Footer';
import { Hero } from '../components/Hero';
import { Navigation } from '../components/Navigation';
import { Ticker } from '../components/Ticker';
import { ContactSection } from '../features/contact/ContactSection';
import { ExperienceSection } from '../features/experience/ExperienceSection';
import { LaunchIntro } from '../features/launch-intro/LaunchIntro';
import { useIntroController } from '../features/launch-intro/useIntroController';
import { MarinaBaySection } from '../features/marina-bay/MarinaBaySection';
import { ProjectsSection } from '../features/projects/ProjectsSection';
import type { Project } from '../features/projects/types';
import { SkillsSection } from '../features/skills/SkillsSection';
import { SpotifySection } from '../features/spotify/SpotifySection';
import { useReveal } from '../hooks/useReveal';

const emptyIntroMedia = { desktop: false, mobile: false };

export function App({ introMedia = emptyIntroMedia }: { introMedia?: IntroMedia }) {
  useReveal();
  const intro = useIntroController(introMedia);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  function openProject(project: Project, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setSelectedProject(project);
  }

  const phase = intro.run?.skipped ? 'skip' : intro.run?.phase;
  const matchesRecordedHero = intro.run?.mode === 'video' && !intro.run.skipped;
  const quoteIndex = intro.capture || matchesRecordedHero ? INTRO_CONFIG.captureQuoteIndex : undefined;

  return (
    <>
      <div className="portfolio-content" inert={intro.blocked} data-launch-phase={phase}>
        <a className="skip-link" href="#main">Skip to content</a>
        <Navigation />
        <Hero quoteIndex={quoteIndex} />
        <main id="main" ref={intro.mainRef} tabIndex={-1}>
          <Ticker />
          <ProjectsSection onOpen={openProject} selectedId={selectedProject?.id ?? null} />
          <SkillsSection />
          <ExperienceSection />
          <SpotifySection />
          <MarinaBaySection />
          <ContactSection />
        </main>
        <Footer onReplayIntro={intro.replay} />
      </div>
      {intro.blocked && <LaunchIntro intro={intro} />}
      {selectedProject && (
        <DetailPanel
          project={selectedProject}
          trigger={triggerRef.current}
          onDismiss={() => setSelectedProject(null)}
        />
      )}
    </>
  );
}
