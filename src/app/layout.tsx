import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { INTRO_BOOT_SCRIPT } from '../config/intro';
import '../styles/global.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://jarrodlow.com'),
  title: 'Jarrod Low — Portfolio',
  description: 'Jarrod Low, Computer Science and Design student at SUTD, on exchange in Hangzhou. Computer vision, LLM evaluation, and systems projects.',
  alternates: { canonical: '/' },
  icons: { icon: { url: '/assets/favicon.svg', type: 'image/svg+xml' } },
  openGraph: {
    type: 'website',
    title: 'Jarrod Low · AI Engineer',
    description: 'Computer vision, LLM evaluation, and systems projects from an SUTD Computer Science and Design student in Hangzhou.',
    url: '/',
    images: '/assets/og.png',
  },
  twitter: { card: 'summary_large_image' },
};

export const viewport: Viewport = { themeColor: '#E8112D', colorScheme: 'light' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: INTRO_BOOT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
