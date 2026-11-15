import { ExperienceRow } from './ExperienceRow';
import { experience } from './experience';

export function ExperienceSection() {
  return (
    <section className="section" id="experience">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Classification</p>
          <p className="mono section-index">SEC · 03</p>
        </div>
        <h2 className="section-title display">Experience</h2>
        <div className="rows">
          {experience.map((entry) => <ExperienceRow key={entry.position} entry={entry} />)}
        </div>
      </div>
    </section>
  );
}
