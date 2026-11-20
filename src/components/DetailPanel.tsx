import { useCallback, useEffect, useRef, useState } from 'react';
import type { Project } from '../features/projects/types';

export function DetailPanel({
  project,
  trigger,
  onDismiss,
}: {
  project: Project;
  trigger: HTMLButtonElement | null;
  onDismiss: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [closing, setClosing] = useState(false);

  const requestClose = useCallback(() => {
    if (closing) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      onDismiss();
      return;
    }
    setClosing(true);
    closeTimerRef.current = setTimeout(onDismiss, 240);
  }, [closing, onDismiss]);

  useEffect(() => {
    const dialog = dialogRef.current!;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.showModal();
    closeRef.current?.focus();
    return () => {
      clearTimeout(closeTimerRef.current);
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [trigger]);

  const stackItems = project.stack.split('·').map((item) => item.trim()).filter(Boolean);

  return (
    <dialog
      ref={dialogRef}
      className={`detail-panel${closing ? ' closing' : ''}`}
      aria-modal="true"
      aria-labelledby="detail-title"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Tab') return;
        const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button, a[href]'));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
    >
      <div
        className={`detail-inner${project.fastest ? ' fastest' : ''}`}
        onAnimationEnd={(event) => {
          if (closing && event.target === event.currentTarget) {
            clearTimeout(closeTimerRef.current);
            onDismiss();
          }
        }}
      >
        <header className="detail-header">
          <span className="mono">
            Project / Round {project.round}
            {project.fastest ? ' · Fastest Lap' : ''}
          </span>
          <button
            ref={closeRef}
            className="detail-close"
            type="button"
            onClick={requestClose}
            aria-label="Close details"
          >
            Close <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="detail-content">
          <h2 id="detail-title" className="detail-title display">{project.title}</h2>
          <div className={`detail-media${project.fastest ? ' fastest' : ''}`}>
            {project.media.kind === 'image' ? (
              <img
                src={project.media.src}
                width={project.media.width}
                height={project.media.height}
                alt={project.media.alt}
              />
            ) : (
              <div className="detail-cover">
                <div className="detail-cover-top mono">
                  <span>Round {project.round}</span>
                  <span className={project.fastest ? 'detail-cover-fastest' : undefined}>
                    {project.fastest ? 'Fastest Lap' : project.category}
                  </span>
                </div>
                <p className="detail-cover-subtitle display">{project.media.subtitle}</p>
                <div className="detail-cover-tags">
                  {stackItems.map((tech) => (
                    <span className="mono" key={tech}>{tech}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
          <p className="detail-description">{project.description}</p>
          <dl className="detail-facts">
            <div><dt>Role</dt><dd>{project.role}</dd></div>
            <div><dt>Stack</dt><dd>{project.stack}</dd></div>
            <div><dt>Year</dt><dd>{project.year}</dd></div>
          </dl>
          <a
            className={`detail-link${project.fastest ? ' fastest' : ''}`}
            href={project.link}
            target="_blank"
            rel="noopener noreferrer"
          >
            {project.linkLabel}
          </a>
        </div>
      </div>
    </dialog>
  );
}
