import type { Project } from './types';

export function ProjectRow({ project, selected, onOpen }: { project: Project; selected: boolean; onOpen: (trigger: HTMLButtonElement) => void }) {
  return (
    <button type="button" className={`classification-row project-row${project.fastest ? ' fastest' : ''}`} aria-haspopup="dialog" aria-expanded={selected} onClick={(event) => onOpen(event.currentTarget)}>
      <span className="classification-position display"><span className="classification-caption">Round</span>{project.round}</span>
      <span className="classification-name">{project.title}</span>
      <span className="classification-meta mono">{project.category}</span>
      <span className="classification-meta mono">{project.year}</span>
      <span className="classification-open" aria-hidden="true">+</span>
    </button>
  );
}
