import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { INTRO_VIDEOS, type IntroVariant, type IntroVideo } from '../config/intro';
import { App } from './App';

function findIntroVideo(viewport: IntroVariant): IntroVideo | null {
  for (const version of ['singaporeWheel', 'legacy'] as const) {
    const files = Object.values(INTRO_VIDEOS[version].media[viewport]);
    if (files.every((file) => existsSync(join(process.cwd(), 'public', file)))) return version;
  }
  return null;
}

export default function Home() {
  return <App introMedia={{ desktop: findIntroVideo('desktop'), mobile: findIntroVideo('mobile') }} />;
}
