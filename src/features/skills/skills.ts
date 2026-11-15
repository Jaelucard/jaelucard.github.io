export interface SkillGroup {
  title: string;
  skills: string[];
}

export const skillGroups: SkillGroup[] = [
  { title: 'Spoken', skills: ['English', 'Chinese', 'Korean'] },
  { title: 'Languages', skills: ['Python', 'C', 'TypeScript', 'Java', 'SQL', 'Lucid HDL'] },
  { title: 'ML', skills: ['PyTorch', 'scikit-learn', 'LightGBM', 'spaCy', 'Ollama'] },
  { title: 'Build', skills: ['FastAPI', 'React', 'Docker', 'Git', 'Linux'] },
  { title: 'Interests', skills: ['Motorsports', 'Dance', 'Video Games', 'Travelling', 'Basketball'] },
];
