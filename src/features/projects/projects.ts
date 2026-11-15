import type { Project } from './types';

export const projects: Project[] = [
  {
    id: 'f1-dashboard', round: '01', title: 'F1 Dashboard', category: 'Web',
    media: { kind: 'image', src: '/assets/projects/f1-dashboard.webp', width: 1200, height: 669, alt: 'F1 Dashboard: live timing leaderboard, flag panel and track map for a Monza session' },
    description: 'Live 2026 F1 timing on OpenF1 data. Track map, leaderboard with gaps, flag panel. FastAPI backend, React front end, WebSocket feed.',
    role: 'Full-Stack Developer', stack: 'React · FastAPI', year: '2026',
    link: 'https://github.com/Jaelucard/F1-Dashboard', linkLabel: 'Visit ↗',
  },
  {
    id: 'genai-text-detection', round: '02', title: 'GenAI Text Detection', category: 'ML', fastest: true,
    media: { kind: 'cover', subtitle: 'Round 02 · Kaggle · P1 Private' },
    description: 'Kaggle AI-generated text detection, team of five. 1st on the private leaderboard, 4th on the public. Classical ML only: scikit-learn, LightGBM, spaCy stylometry, adversarial validation.',
    role: 'ML · Team of 5', stack: 'scikit-learn · LightGBM', year: '2026',
    link: 'https://github.com/Jaelucard', linkLabel: 'GitHub ↗',
  },
  {
    id: 'llm-eval-lab', round: '03', title: 'LLM Eval Lab', category: 'Tooling',
    media: { kind: 'cover', subtitle: 'Round 03 · Regression Testing' },
    description: 'Local-first LLM regression testing. Content-addressed benchmark suites, deterministic or LLM-as-judge scoring, statistical baseline comparison, SQLite run history, CLI and REST API with a CI exit-code contract, React dashboard.',
    role: 'Creator', stack: 'Python · FastAPI · React', year: '2026',
    link: 'https://github.com/Jaelucard/llm-eval-lab', linkLabel: 'Visit ↗',
  },
  {
    id: 'tetrish', round: '04', title: 'TetriSH', category: 'Systems',
    media: { kind: 'image', src: '/assets/projects/tetrish.webp', width: 1132, height: 739, alt: 'TetriSH: ncurses client showing a two-player battle royale board, next and hold queues, and the controls list' },
    description: 'Terminal Battle-Royale Tetris in C. Launcher shell, epoll game daemon, logger daemon, admin CLI, ncurses client and replay viewer, over a self-designed authenticated and encrypted session protocol.',
    role: 'Systems · Team of 3', stack: 'C · OpenSSL · epoll', year: '2026',
    link: 'https://github.com/Jaelucard/tetrish', linkLabel: 'Visit ↗',
  },
  {
    id: 'aura-wall', round: '05', title: 'Aura Wall', category: 'Hardware',
    media: { kind: 'image', src: '/assets/projects/aura-wall.webp', width: 1200, height: 800, alt: 'Aura Wall: presenting the LED installation concept, with the silhouette and mood renders on the projector' },
    description: 'Interactive LED installation. An ESP camera and computer vision track movement and paint a silhouette and mood across nine LED panels on custom 3D-printed mounts.',
    role: 'CV + Build', stack: 'ESP32-CAM · OpenCV', year: '2025',
    link: 'https://github.com/Jaelucard', linkLabel: 'GitHub ↗',
  },
];
