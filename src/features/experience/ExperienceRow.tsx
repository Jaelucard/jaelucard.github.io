import type { Experience } from './experience';

export function ExperienceRow({ entry }: { entry: Experience }) {
  return (
    <div className="row reveal">
      <div className="row-pos display">{entry.position}</div>
      <div className="row-entry"><strong>{entry.title}</strong><span>{entry.organization}</span></div>
      <div className="row-note">{entry.note}</div>
      <div className="row-time mono">{entry.time}</div>
    </div>
  );
}
