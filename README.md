# Jarrod Low's portfolio

Personal portfolio at [jarrodlow.com](https://jarrodlow.com), inspired by Scuderia Ferrari race-weekend graphics. Built with Next.js, React and TypeScript.

## Getting started

Use Node.js 24 or newer and npm:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. To check and preview the production build:

```sh
npm test
npm run build
npm run preview
```

Next.js checks TypeScript and exports the static site to `out/`. The preview command serves that directory at `http://127.0.0.1:4173`.

## File guide

```text
package.json                         Dependencies and development/build scripts
package-lock.json                    Locked dependency versions for npm ci
.gitignore                           Excludes dependencies and generated builds
tsconfig.json                        TypeScript compiler settings
next.config.ts                       Next.js static export configuration
.github/workflows/deploy.yml         GitHub Pages build and deployment workflow
CNAME                                Repository-root custom-domain file
public/
  CNAME                              Custom-domain file copied into the build
  .nojekyll                          Allows GitHub Pages to serve the _next assets
  assets/
    favicon.svg                      Browser tab icon (vector path)
    og.png                           Social sharing preview image
    projects/                        Project images in WebP format
    marina-bay/                      Original circuit GeoJSON and MIT source notice
docs/
  marina-bay-game-plan.md            Game scope, research, implementation and release record
scripts/
  preview.mjs                        Local server for the static export
services/spotify/                    Cloudflare Worker, authorization helper and tests
tests/                               Game, frontend playback and daily quote tests
src/
  app/
    layout.tsx                       Site metadata, global styles and intro gate
    page.tsx                         Portfolio page and deployed intro asset availability
    App.tsx                          Portfolio sections, detail panel and intro controls
  config/
    intro.ts                         Intro timing, media contract and pre-paint gate
  components/
    Navigation.tsx                   Top navigation, active scroll-spy and mobile menu drawer
    Hero.tsx                         Introduction, headline and quick stats
    Ticker.tsx                       Seamless scrolling text strip
    DetailPanel.tsx                  Slide-over project details drawer
    classification.css               Classification boards, experience disclosure and detail panel styles
    Footer.tsx                       Footer links, location and founding year
  features/
    launch-intro/                    First-visit cinematic, fallback and video-to-Hero handoff
    marina-bay/                      Full-layout 2D driving game, controls, scoring and renderer
    projects/
      projects.ts                    Project entries and their content
      types.ts                       Project and project-media types
      ProjectRow.tsx                 Reusable project classification row
      ProjectsSection.tsx            Projects classification board
    skills/
      skills.ts                      Skill groups and their entries
      SkillsSection.tsx              About text and skills section layout
    experience/
      experience.ts                  Experience entries and their type
      ExperienceRow.tsx              Inline expandable experience row
      ExperienceSection.tsx          Experience classification board
    contact/
      ContactSection.tsx             Contact text, email and availability
    spotify/
      SpotifySection.tsx             Compact standby bar when off air; broadcast card when active
      playback.ts                    Playback validation and time formatting
      polling.ts                     Visibility-aware adaptive playback polling
      spotify.css                    Standby bar, broadcast styling and decorative synth motion
      spotify-logo-white.svg         Spotify attribution graphic
    radio-quotes/
      RadioQuote.tsx                 Daily quote display and midnight refresh
      quotes.ts                      Radio excerpts, speakers and sources
      schedule.ts                    Singapore-day rotation and next midnight
  hooks/
    useNavScroll.ts                  Navigation scroll state and active-section scroll-spy
    useReveal.ts                     Scroll reveals and motion fallbacks
  styles/
    global.css                       Design tokens, site styles and responsive rules
```

## Common updates

- **Add or edit a project:** update `src/features/projects/projects.ts`. `types.ts` lists the required fields. For an image, place a WebP file in `public/assets/projects/` and use an `/assets/projects/...` path, image dimensions and alt text in its `media` entry. A text cover uses `kind: 'cover'` and a subtitle.
- **Update skills or experience:** edit `src/features/skills/skills.ts` or `src/features/experience/experience.ts`.
- **Update the introduction or contact details:** edit `Hero.tsx`, `SkillsSection.tsx`, `ContactSection.tsx`, or `Footer.tsx` as appropriate. The about text is in `SkillsSection.tsx`, not the skills data file.
- **Update the daily radio quotes:** edit `src/features/radio-quotes/quotes.ts`. Quotes rotate in list order at midnight Singapore time; changing the list can change the quote selected for a given day.
- **Change appearance or layout:** edit `src/styles/global.css`; change a component when its markup needs to change.
- **Update search or sharing metadata:** edit `src/app/layout.tsx`. Replace `public/assets/og.png` to change the social preview image.

Run `npm test` and `npm run build` after changes to check the feature tests, TypeScript and production build.

## Cockpit launch intro

The cockpit intro plays on homepage visits and reloads, with a fade from the neutral gear display into the Hero. Use `/?intro=1` or the footer's **Replay intro** button to replay it. The automatic intro respects reduced motion, Save-Data, anchor links and browser history restoration. Use `/?capture=hero` for a clean Hero capture without the navigation or scroll cue.

The build selects each viewport's render when its WebM, MP4 and WebP poster are present in `public/media/`. The required filenames and the handoff time are in `src/config/intro.ts`. With no render for a viewport, the portfolio plays the built-in animated sequence.

## Marina Bay mini racer

The `#marina-bay` section sits directly below the Spotify player and provides a fixed top-down driving game with the full 19-turn Marina Bay route. Its preview is prerendered with the portfolio; the game loads after **Start your lap**.

| Controls | Action |
| --- | --- |
| `W` / `↑` | Accelerate |
| `S` / `↓` | Brake, then reverse slowly |
| `A` / `D`, `←` / `→` | Steer |
| `P` / `Escape` | Toggle pause/resume with `P`; pause with `Escape` |
| `R` | Restart the attempt while retaining completed results and the browser best |

Hold touch buttons together to steer and accelerate. Driving keys apply while the Canvas has focus; leaving the game, hiding the page or scrolling the game off screen pauses the session. The timer begins when the car moves. A valid lap requires all 63 interior checkpoints in order and a forward finish crossing.

All 116 source vertices are preserved and reversed into race direction, with one uniform scale to 4,927 game metres. The community trace and turn labels are approximate; the 36 m arcade road width supports forgiving handling. Source data and the full MIT notice are in [`public/assets/marina-bay/`](public/assets/marina-bay/).

Maintain motion/scoring in `src/features/marina-bay/simulation.ts`, route geometry in `track-data.ts` and `track.ts`, drawing in `renderer.ts`, and UI/styling in the feature's React/CSS files. Best laps use a versioned local-storage record in `storage.ts`; update the rules version when scoring changes make earlier records incomparable.

Run `node --test tests/marina-bay-*.test.mjs` for focused geometry, simulation and storage checks, then `npm test` and `npm run build`. See the [complete game plan and release record](docs/marina-bay-game-plan.md) for source attribution, tool/skill research, module responsibilities, validation gates and known limitations. Browser QA and deployment status are recorded there separately from implementation status.

`npm run test:browser` runs the Chromium desktop and mobile suite after a production build. Install its browser with `npx playwright install chromium` on a machine that supports browser execution. The pull-request workflow in `.github/workflows/browser-checks.yml` installs Chromium automatically and retains screenshots, a report and failure traces. Playwright is a development dependency and is not included in the website bundle.

## Publishing

GitHub Pages uses **GitHub Actions** as its publishing source. A push to `main` runs `.github/workflows/deploy.yml`, which installs the locked dependencies, checks the site and deploys the `out/` export. The workflow can also run manually from GitHub Actions. Keep `jarrodlow.com` configured in the repository's Pages settings.

## Spotify Radio Check

The broadcast-style tracker is in `src/features/spotify/`. Its public status endpoint is provided by the separate Cloudflare Worker in `services/spotify/`; it shows an unavailable state until configured. See [the service setup guide](services/spotify/README.md) for its files, local checks, authorization and publishing steps. Spotify credentials must never be added to the frontend or repository.
