export interface Experience {
  position: string;
  title: string;
  organization: string;
  note: string;
  time: string;
}

export const experience: Experience[] = [
  {
    position: 'P1', title: 'B.Eng Computer Science and Design',
    organization: 'SUTD, Singapore · exchange at Zhejiang University 2026–27',
    note: 'Machine learning, software construction, operating systems, network security, computation structures.',
    time: '2023 — 2027',
  },
  {
    position: 'P2', title: 'Computer Vision Intern', organization: 'MolarData, Hangzhou',
    note: 'Trained and evaluated computer vision models for a RAG-based recognition and decision pipeline.',
    time: '2025',
  },
  {
    position: 'P3', title: 'Database Management Assistant', organization: 'MINDEF, Singapore',
    note: 'Maintained the SAF Service Injury database and built an Excel VBA workflow that replaced manual record handling.',
    time: '2022 — 2024',
  },
];
