import type { Experience } from './experience';

export function ExperienceRow({
  entry,
  expanded,
  onToggle,
}: {
  entry: Experience;
  expanded: boolean;
  onToggle: () => void;
}) {
  const panelId = `experience-panel-${entry.position.toLowerCase()}`;

  return (
    <div className={`experience-item${expanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="classification-row experience-row"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span className="classification-position display">{entry.position}</span>
        <span className="classification-entry">
          <strong className="classification-name">{entry.title}</strong>
          <span className="classification-org">{entry.organization}</span>
        </span>
        <span className="classification-meta mono">{entry.time}</span>
        <span className="classification-open" aria-hidden="true">+</span>
      </button>
      <div id={panelId} className="experience-panel" data-open={expanded} aria-hidden={!expanded}>
        <div className="experience-panel-inner">
          <p className="experience-note">{entry.note}</p>
        </div>
      </div>
    </div>
  );
}
