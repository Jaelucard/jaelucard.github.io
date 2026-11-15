# Jarrod Low's portfolio

Personal portfolio inspired by Scuderia Ferrari race-weekend graphics. Built with React, TypeScript and Vite.

## Development

Requires Node.js 24 or newer and npm.

```sh
npm ci
npm run dev
```

`npm run build` checks TypeScript, builds the client, and renders the page to static HTML in `dist/`. Use `npm run preview` to serve that production build locally.

## Structure

- `src/app/` assembles the page and contains the browser and static rendering entry points.
- `src/components/` contains site-wide sections.
- `src/features/` groups projects, skills, experience and contact. Edit `projects/projects.ts` or `experience/experience.ts` to update entries; their components render them.
- `src/hooks/` contains the navigation and scroll-reveal behavior.
- `src/styles/global.css` contains the existing design tokens, responsive styles and motion settings.
- `public/assets/` contains images and the favicon, copied unchanged into the build.

## Publishing to GitHub Pages

The included GitHub Actions workflow builds `dist/` and deploys it to GitHub Pages when changes are pushed to `main`. Configure the repository's Pages source as **GitHub Actions** and retain the custom domain in Pages settings. Vite source files cannot be published directly with branch-based Pages publishing because they require a build.
