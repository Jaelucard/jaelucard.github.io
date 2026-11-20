import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { INTRO_CONFIG } from '../config/intro';
import { App } from './App';

function hasIntroMedia(viewport: keyof typeof INTRO_CONFIG.media) {
  return Object.values(INTRO_CONFIG.media[viewport]).every((file) => existsSync(join(process.cwd(), 'public', file)));
}

export default function Home() {
  return <App introMedia={{ desktop: hasIntroMedia('desktop'), mobile: hasIntroMedia('mobile') }} />;
}
