import { StrictMode } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import { App } from './App';
import '../styles/global.css';

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');

const app = <StrictMode><App /></StrictMode>;
if (root.hasChildNodes()) {
  hydrateRoot(root, app);
} else {
  createRoot(root).render(app);
}
