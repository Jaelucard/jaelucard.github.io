import { useState } from 'react';
import { ExperienceRow } from './ExperienceRow';
import { experience } from './experience';

export function ExperienceSection() {
  const [openPosition, setOpenPosition] = useState<string | null>(null);

  return (
    <section className="section" id="experience">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Classification</p>
          <p className="mono section-index">SEC · 03</p>
        </div>
        <h2 className="section-title display">Experience</h2>
        <div className="classification-list">
          {experience.map((entry) => {
            const expanded = openPosition === entry.position;
            return (
              <ExperienceRow
                key={entry.position}
                entry={entry}
                expanded={expanded}
                onToggle={() => setOpenPosition((current) => (current === entry.position ? null : entry.position))}
              />
            );
          })}
        </div>
      </div>
    </section>
  );
}
