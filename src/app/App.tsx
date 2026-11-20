import { useRef, useState } from 'react';
import '../components/classification.css';
import { DetailPanel } from '../components/DetailPanel';
import { Footer } from '../components/Footer';
import { Hero } from '../components/Hero';
import { Navigation } from '../components/Navigation';
import { Ticker } from '../components/Ticker';
import { ContactSection } from '../features/contact/ContactSection';
import { ExperienceSection } from '../features/experience/ExperienceSection';
import { MarinaBaySection } from '../features/marina-bay/MarinaBaySection';
import { ProjectsSection } from '../features/projects/ProjectsSection';
import type { Project } from '../features/projects/types';
import { SkillsSection } from '../features/skills/SkillsSection';
import { SpotifySection } from '../features/spotify/SpotifySection';
import { useReveal } from '../hooks/useReveal';

export function App() {
  useReveal();
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  function openProject(project: Project, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setSelectedProject(project);
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <Navigation />
      <Hero />
      <main id="main">
        <Ticker />
        <ProjectsSection onOpen={openProject} selectedId={selectedProject?.id ?? null} />
        <SkillsSection />
        <ExperienceSection />
        <SpotifySection />
        <MarinaBaySection />
        <ContactSection />
      </main>
      <Footer />
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
