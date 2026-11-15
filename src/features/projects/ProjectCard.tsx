import type { Project } from './types';

export function ProjectCard({ project }: { project: Project }) {
  const { media } = project;
  return (
    <article className={`gp-card${project.fastest ? ' fastest' : ''} reveal`}>
      <header className="gp-head">
        <div className="gp-meta"><span>Round</span><strong>{project.round}</strong></div>
        <h3 className="gp-title display">{project.title}</h3>
        <div className="gp-meta right"><span>Type</span><strong>{project.category}</strong></div>
      </header>
      <div className="gp-media">
        {media.kind === 'image' ? (
          <img src={media.src} width={media.width} height={media.height} loading="lazy" alt={media.alt} />
        ) : (
          <div className="gp-cover">
            <span className="display">{project.title}</span>
            <span className="mono">{media.subtitle}</span>
          </div>
        )}
      </div>
      <p className="gp-note">{project.description}</p>
      <footer className="gp-cells">
        <div className="cell"><span className="cell-label">Role</span><span className="cell-value">{project.role}</span></div>
        <div className="cell"><span className="cell-label">Stack</span><span className="cell-value">{project.stack}</span></div>
        <div className="cell"><span className="cell-label">Year</span><span className="cell-value">{project.year}</span></div>
        <a className="cell" href={project.link} target="_blank" rel="noopener noreferrer"><span className="cell-label">Link</span><span className="cell-value">{project.linkLabel}</span></a>
      </footer>
    </article>
  );
}
