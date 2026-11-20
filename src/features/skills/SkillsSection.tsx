import { skillGroups } from './skills';

export function SkillsSection() {
  return (
    <section className="section quali" id="skills">
      <div className="wrap">
        <div className="section-head">
          <p className="eyebrow">Driver Profile</p>
          <p className="mono section-index">SEC · 02</p>
        </div>


        <div className="quali-poster reveal">
          <p className="eyebrow">Singapore University of Technology and Design · Computer Science and Design</p>
          <h2 className="quali-title display">About <em>&amp;</em> Skills</h2>
          <p className="eyebrow">Hangzhou, China</p>
        </div>

        <div className="quali-cols">
          <div className="reveal">
            <h3 className="eyebrow">Profile</h3>
            <p>I am a third-year Computer Science and Design student at SUTD, currently based in Hangzhou
            for a year of exchange and startup work. I started out in cybersecurity and open-source
            intelligence, then followed the problems that held my attention longer: how machines see,
            how language models fail, and how to catch those failures before a user ever does. I have
            trained computer vision models at a Chinese AI startup, placed first on the private
            leaderboard of a Kaggle AI-generated text detection competition with a team of five, and I
            am building an evaluation tool that stress-tests LLMs the way a scrutineer checks a car
            before it leaves the garage. I want to be the AI engineer who ships the system and then
            proves it holds up.</p>
            <p>Away from the keyboard I freestyle in hip hop battles, play basketball recreationally, and
            give most of what is left to motorsport. I race in sim, study race craft, and carry one
            long-term ambition outside of tech: to fund my own seat in a GT3 championship in Europe.
            The same instinct runs through all of it. Find the limit, work out why it is there, then
            move it.</p>
          </div>

          <div className="reveal">
            <h3 className="eyebrow">Skills</h3>
            {skillGroups.map((group) => (
              <div className="skill-group" key={group.title}>
                <h4>{group.title}</h4>
                <div className="chips">
                  {group.skills.map((skill) => <span className="chip" key={skill}>{skill}</span>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
