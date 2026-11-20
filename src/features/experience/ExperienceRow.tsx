import type { Experience } from './experience';

export function ExperienceRow({ entry, selected, onOpen }: { entry: Experience; selected: boolean; onOpen: (trigger: HTMLButtonElement) => void }) {
  return (
    <button type="button" className="classification-row experience-row" aria-haspopup="dialog" aria-expanded={selected} onClick={(event) => onOpen(event.currentTarget)}>
      <span className="classification-position display">{entry.position}</span>
      <span className="classification-entry"><strong className="classification-name">{entry.title}</strong><span>{entry.organization}</span></span>
      <span className="classification-meta mono">{entry.time}</span>
      <span className="classification-open" aria-hidden="true">+</span>
    </button>
  );
}
