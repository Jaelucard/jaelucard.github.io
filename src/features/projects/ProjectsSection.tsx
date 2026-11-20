import { ProjectRow } from './ProjectRow';
import { projects } from './projects';
import type { Project } from './types';

export function ProjectsSection({
  onOpen,
  selectedId,
}: {
  onOpen: (project: Project, trigger: HTMLButtonElement) => void;
  selectedId: string | null;
}) {
  return (
    <section className="section" id="projects">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Selected Work</p>
          <p className="mono section-index">SEC · 01</p>
        </div>
        <h2 className="section-title display red">Projects</h2>
        <div className="classification-list">
          {projects.map((project) => (
            <ProjectRow
              key={project.id}
              project={project}
              selected={selectedId === project.id}
              onOpen={(trigger) => onOpen(project, trigger)}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
