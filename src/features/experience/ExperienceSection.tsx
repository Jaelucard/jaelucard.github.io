import { ExperienceRow } from './ExperienceRow';
import { experience } from './experience';
import type { Selection } from '../../components/DetailPanel';

export function ExperienceSection({ onOpen, selected }: { onOpen: (selection: Selection, trigger: HTMLButtonElement) => void; selected: Selection | null }) {
  return (
    <section className="section" id="experience">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Classification</p>
          <p className="mono section-index">SEC · 03</p>
        </div>
        <h2 className="section-title display">Experience</h2>
        <div className="classification-list">
          {experience.map((entry) => <ExperienceRow key={entry.position} entry={entry} selected={selected?.kind === 'experience' && selected.item.position === entry.position} onOpen={(trigger) => onOpen({ kind: 'experience', item: entry }, trigger)} />)}
        </div>
      </div>
    </section>
  );
}
