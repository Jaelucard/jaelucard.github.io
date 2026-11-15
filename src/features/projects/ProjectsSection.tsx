import { ProjectCard } from './ProjectCard';
import { projects } from './projects';

export function ProjectsSection() {
  return (
    <section className="section" id="projects">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Selected Work</p>
          <p className="mono section-index">SEC · 01</p>
        </div>
        <h2 className="section-title display red">Projects</h2>
        <div className="gp-grid">
          {projects.map((project) => <ProjectCard key={project.id} project={project} />)}
          {projects.length % 2 === 1 && (
            <article className="gp-card ghost reveal"><span className="mono">[ + next round ]</span></article>
          )}
        </div>
      </div>
    </section>
  );
}
