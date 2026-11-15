import { Footer } from '../components/Footer';
import { Hero } from '../components/Hero';
import { Navigation } from '../components/Navigation';
import { Ticker } from '../components/Ticker';
import { ContactSection } from '../features/contact/ContactSection';
import { ExperienceSection } from '../features/experience/ExperienceSection';
import { ProjectsSection } from '../features/projects/ProjectsSection';
import { SkillsSection } from '../features/skills/SkillsSection';
import { useNavScroll } from '../hooks/useNavScroll';
import { useReveal } from '../hooks/useReveal';

export function App() {
  useNavScroll();
  useReveal();

  return (
    <>
      <Navigation />
      <Hero />
      <Ticker />
      <ProjectsSection />
      <SkillsSection />
      <ExperienceSection />
      <ContactSection />
      <Footer />
    </>
  );
}
