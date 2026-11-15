export type ProjectMedia =
  | { kind: 'image'; src: string; width: number; height: number; alt: string }
  | { kind: 'cover'; subtitle: string };

export interface Project {
  id: string;
  round: string;
  title: string;
  category: string;
  media: ProjectMedia;
  description: string;
  role: string;
  stack: string;
  year: string;
  link: string;
  linkLabel: string;
  fastest?: boolean;
}
