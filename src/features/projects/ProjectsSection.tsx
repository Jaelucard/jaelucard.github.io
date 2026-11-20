import { ProjectRow } from './ProjectRow';
import { projects } from './projects';
import type { Selection } from '../../components/DetailPanel';

export function ProjectsSection({ onOpen, selected }: { onOpen: (selection: Selection, trigger: HTMLButtonElement) => void; selected: Selection | null }) {
  return (
    <section className="section" id="projects">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Selected Work</p>
          <p className="mono section-index">SEC · 01</p>
        </div>
        <h2 className="section-title display red">Projects</h2>
        <div className="classification-list">
          {projects.map((project) => <ProjectRow key={project.id} project={project} selected={selected?.kind === 'project' && selected.item.id === project.id} onOpen={(trigger) => onOpen({ kind: 'project', item: project }, trigger)} />)}
        </div>
      </div>
    </section>
  );
}
