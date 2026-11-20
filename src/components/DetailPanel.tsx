import { useEffect, useRef } from 'react';
import type { Experience } from '../features/experience/experience';
import type { Project } from '../features/projects/types';

export type Selection = { kind: 'project'; item: Project } | { kind: 'experience'; item: Experience };

export function DetailPanel({ selection, trigger, onDismiss }: { selection: Selection; trigger: HTMLButtonElement | null; onDismiss: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current!;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.showModal();
    closeRef.current?.focus();
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [trigger]);

  const item = selection.item;
  return (
    <dialog ref={dialogRef} className="detail-panel" aria-modal="true" aria-labelledby="detail-title" onCancel={(event) => { event.preventDefault(); onDismiss(); }} onClick={(event) => { if (event.target === event.currentTarget) onDismiss(); }} onKeyDown={(event) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button, a[href]'));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }}>
      <div className="detail-inner">
        <header className="detail-header">
          <span className="mono">{selection.kind === 'project' ? `Project / Round ${selection.item.round}` : `Experience / ${selection.item.position}`}</span>
          <button ref={closeRef} className="detail-close" type="button" onClick={onDismiss} aria-label="Close details">Close <span aria-hidden="true">×</span></button>
        </header>
        <div className="detail-content">
          <h2 id="detail-title" className="detail-title display">{item.title}</h2>
          {selection.kind === 'project' ? (
            <>
              <div className={`detail-media${selection.item.fastest ? ' fastest' : ''}`}>
                {selection.item.media.kind === 'image' ? <img src={selection.item.media.src} width={selection.item.media.width} height={selection.item.media.height} alt={selection.item.media.alt} /> : <div className="detail-cover"><span className="display">{item.title}</span><span className="mono">{selection.item.media.subtitle}</span></div>}
              </div>
              <p className="detail-description">{selection.item.description}</p>
              <dl className="detail-facts">
                <div><dt>Role</dt><dd>{selection.item.role}</dd></div>
                <div><dt>Stack</dt><dd>{selection.item.stack}</dd></div>
                <div><dt>Year</dt><dd>{selection.item.year}</dd></div>
              </dl>
              <a className="detail-link" href={selection.item.link} target="_blank" rel="noopener noreferrer">{selection.item.linkLabel}</a>
            </>
          ) : (
            <>
              <p className="detail-organization">{selection.item.organization}</p>
              <p className="detail-description">{selection.item.note}</p>
              <dl className="detail-facts"><div><dt>Dates</dt><dd>{selection.item.time}</dd></div></dl>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}
