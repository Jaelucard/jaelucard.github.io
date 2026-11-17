# Jarrod Low's portfolio

Personal portfolio at [jarrodlow.com](https://jarrodlow.com), inspired by Scuderia Ferrari race-weekend graphics. Built with React, TypeScript and Vite.

## Getting started

Use Node.js 24 or newer and npm:

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. To check and preview the production build:

```sh
npm test
npm run build
npm run preview
```

The build checks TypeScript, creates the client files, and pre-renders the page into `dist/index.html`. React hydrates that HTML in the browser to enable interactive behavior. `dist/` is generated and should not be edited directly.

## File guide

```text
index.html                           Page shell, metadata, fonts and app root
package.json                         Dependencies and development/build scripts
package-lock.json                    Locked dependency versions for npm ci
.gitignore                           Excludes dependencies and generated builds
tsconfig.json                        TypeScript compiler settings
vite.config.ts                       Vite configuration and React plugin
.github/workflows/deploy.yml         GitHub Pages build and deployment workflow
CNAME                                Repository-root custom-domain file
public/
  CNAME                              Custom-domain file copied into the build
  assets/
    favicon.svg                      Browser tab icon
    og.png                           Social sharing preview image
    projects/                        Project images in WebP, PNG and JPEG formats
    marina-bay/                      Original circuit GeoJSON and MIT source notice
docs/
  marina-bay-game-plan.md            Game scope, research, implementation and release record
scripts/
  prerender.mjs                      Inserts rendered React markup into dist/index.html
services/spotify/                    Cloudflare Worker, authorization helper and tests
tests/                               Game, frontend playback and daily quote tests
src/
  app/
    App.tsx                          Assembles the page and initializes behavior hooks
    main.tsx                         Browser entry point; renders or hydrates the app
    entry-server.tsx                 Renders the app to HTML for the production build
  components/
    Navigation.tsx                   Top navigation and section links
    Hero.tsx                         Introduction, headline and quick stats
    Ticker.tsx                       Scrolling text strip
    Footer.tsx                       Footer links, location and current year
  features/
    marina-bay/                      Full-layout 2D driving game, controls, scoring and renderer
    projects/
      projects.ts                    Project entries and their content
      types.ts                       Project and project-media types
      ProjectCard.tsx                Reusable project card layout
      ProjectsSection.tsx            Project grid and placeholder card
    skills/
      skills.ts                      Skill groups and their entries
      SkillsSection.tsx              About text and skills section layout
    experience/
      experience.ts                  Experience entries and their type
      ExperienceRow.tsx              Reusable experience row
      ExperienceSection.tsx          Experience section layout
    contact/
      ContactSection.tsx             Contact text, email and availability
    spotify/
      SpotifySection.tsx            Broadcast tracker and interaction
      playback.ts                    Playback validation and time formatting
      polling.ts                     Automatic playback checks and page-return refresh
      spotify.css                    Broadcast styling and decorative synth motion
      spotify-logo-white.svg         Spotify attribution graphic
    radio-quotes/
      RadioQuote.tsx                 Daily quote display and midnight refresh
      quotes.ts                      Radio excerpts, speakers and sources
      schedule.ts                    Singapore-day rotation and next midnight
  hooks/
    useNavScroll.ts                  Navigation background on scroll
    useReveal.ts                     Scroll reveals and motion fallbacks
  styles/
    global.css                       Design tokens, site styles and responsive rules
```

The workflow publishes the contents of `dist/`, including files copied from `public/`. GitHub Pages stores the custom domain in its settings when publishing through Actions; keep those settings configured for `jarrodlow.com`.

## Common updates

- **Add or edit a project:** update `src/features/projects/projects.ts`. `types.ts` lists the required fields. For an image, place it in `public/assets/projects/` and use an `/assets/projects/...` path, image dimensions and alt text in its `media` entry. A text cover uses `kind: 'cover'` and a subtitle. The grid shows a placeholder when there is an odd number of projects.
- **Update skills or experience:** edit `src/features/skills/skills.ts` or `src/features/experience/experience.ts`.
- **Update the introduction or contact details:** edit `Hero.tsx`, `SkillsSection.tsx`, `ContactSection.tsx`, or `Footer.tsx` as appropriate. The about text is in `SkillsSection.tsx`, not the skills data file.
- **Update the daily radio quotes:** edit `src/features/radio-quotes/quotes.ts`. Quotes rotate in list order at midnight Singapore time; changing the list can change the quote selected for a given day.
- **Change appearance or layout:** edit `src/styles/global.css`; change a component when its markup needs to change.
- **Update search or sharing metadata:** edit the title and meta tags in `index.html`. Replace `public/assets/og.png` to change the social preview image.

Run `npm test` and `npm run build` after changes to check the feature tests, TypeScript and production build.

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

GitHub Pages uses **GitHub Actions** as its publishing source. A push to `main` runs `.github/workflows/deploy.yml`, which installs the locked dependencies, builds the site, and deploys `dist/`. The workflow can also be run manually from GitHub Actions. Keep the custom domain configured in the repository's Pages settings.

The source files cannot be published directly from the repository root as a branch-based Pages site: Vite must build them first.

## Spotify Radio Check

The broadcast-style tracker is in `src/features/spotify/`. Its public status endpoint is provided by the separate Cloudflare Worker in `services/spotify/`; it shows an unavailable state until configured. See [the service setup guide](services/spotify/README.md) for its files, local checks, authorization and publishing steps. Spotify credentials must never be added to the frontend or repository.
