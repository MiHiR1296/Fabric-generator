import { useCallback, useMemo, useState } from 'react';
import MultiThreadImageEditor from './yarnseamless/MultiThreadImageEditor';
import MultiFragmentEditor from './yarnseamless/MultiFragmentEditor';
import type { YarnAsset } from '../domain/types';
import type { LibraryYarnEntry, YarnOrientation } from '../utils/parserApi';

/* ---------------------------------------------------------------------------
 * Step 1 — yarnseamless flow at full page.
 *
 * Layout intent (per user feedback 2026-05-13):
 *   The yarnseamless UI is shown EXACTLY as in the original yarnseamless app.
 *   Same colours, same placements, same internal scroll. The only addition is
 *   a slim "Saved yarn library" strip at the very top — a horizontal scroll
 *   of saved yarns with Import buttons.
 *
 *   No card-in-card wrapping. No max-height frame. The editor takes the full
 *   wizard-page area (which is itself `flex: 1 1 auto` of the studio-shell).
 *
 *   When the user finishes processing in MultiThreadImageEditor, the same
 *   page swaps to MultiFragmentEditor (same area, no relayout, no navigation).
 *   When MFE saves to library, hitting Cancel returns the user to the upload
 *   view and refreshes the library strip.
 * ------------------------------------------------------------------------- */

interface YarnLibraryStepProps {
  assets: YarnAsset[];
  busy: boolean;
  message: string;
  // The legacy upload props are still passed by App.tsx but we don't render
  // their UI in Step 1 — the yarnseamless flow is the only entry now.
  onUpload: (files: File[], orientation: YarnOrientation) => void;
  onRetry: (assetId: string, orientation: YarnOrientation) => void;
  onDelete: (assetId: string) => void;
  onRefresh: () => void;
  library?: LibraryYarnEntry[];
  importingYarnId?: string | null;
  onImportFromLibrary?: (yarnId: string) => Promise<void> | void;
  onDeleteFromLibrary?: (yarnId: string) => Promise<void> | void;
  onRefreshLibrary?: () => Promise<void> | void;
}

export default function YarnLibraryStep({
  assets,
  onRefresh,
  library = [],
  importingYarnId = null,
  onImportFromLibrary,
  onDeleteFromLibrary,
  onRefreshLibrary,
}: YarnLibraryStepProps) {
  // The yarnseamless flow has two real screens: MultiThreadImageEditor (until
  // the user clicks Next) and MultiFragmentEditor (after). We carry the
  // fragments[] hand-off in local state — same shape as yarnseamless's App.jsx
  // `inputMode` toggle, but without the third "single image" mode (we don't
  // port that flow).
  const [fragments, setFragments] = useState<any[]>([]);
  const [brushSize, setBrushSize] = useState(20);

  const importedLibraryIds = useMemo(() => {
    const ids = new Set<string>();
    for (const asset of assets) {
      const libraryId = (asset as any)?.bandMeta?.library_yarn_id;
      if (typeof libraryId === 'string') ids.add(libraryId);
    }
    return ids;
  }, [assets]);

  const backToUpload = useCallback(() => {
    setFragments([]);
    if (onRefreshLibrary) onRefreshLibrary();
    onRefresh();
  }, [onRefreshLibrary, onRefresh]);

  return (
    <section className="ys-step" data-testid="yarn-library-step">
      {/* Slim library strip — only shows if there's anything saved.
       *  Horizontal scroll so it never pushes the editor downward. */}
      {library.length > 0 && onImportFromLibrary ? (
        <div className="ys-library-strip" data-testid="yarn-library-shared">
          <div className="ys-library-strip__header">
            <span className="eyebrow">Saved yarn library</span>
            <span className="status-pill status-pill--source">{library.length} saved</span>
            <span className="status-pill status-pill--online">
              {importedLibraryIds.size} imported into this project
            </span>
            <div className="ys-library-strip__spacer" />
            <button
              type="button"
              className="button button--tiny button--ghost"
              onClick={() => onRefreshLibrary?.()}
              data-testid="yarn-library-refresh"
            >
              Refresh
            </button>
          </div>
          <div className="ys-library-strip__items">
            {library.map((entry) => {
              const isImported = importedLibraryIds.has(entry.id);
              const isImporting = importingYarnId === entry.id;
              return (
                <article
                  className="ys-library-card"
                  key={entry.id}
                  data-testid="yarn-library-card"
                >
                  {entry.thumbnailUrl ? (
                    <img
                      src={entry.thumbnailUrl}
                      alt={`${entry.label || entry.id} thumbnail`}
                    />
                  ) : (
                    <div className="ys-library-card__placeholder" />
                  )}
                  <div className="ys-library-card__body">
                    <h4>{entry.label || entry.id}</h4>
                    <p className="muted">
                      {entry.widthMm != null ? `${entry.widthMm.toFixed(2)} mm` : '—'}
                      {entry.dpi != null ? ` · ${entry.dpi} dpi` : ''}
                    </p>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <button
                        type="button"
                        className={`button button--tiny ${
                          isImported ? 'button--ghost' : 'button--accent'
                        }`}
                        onClick={() => onImportFromLibrary(entry.id)}
                        disabled={isImporting || isImported}
                        data-testid={`yarn-library-import-${entry.id}`}
                      >
                        {isImporting ? 'Importing…' : isImported ? 'Imported ✓' : 'Import'}
                      </button>
                      {onDeleteFromLibrary && (
                        <button
                          type="button"
                          className="button button--tiny button--ghost"
                          title={`Delete ${entry.label || entry.id} from library`}
                          aria-label={`Delete ${entry.label || entry.id} from library`}
                          onClick={() => {
                            const ok = window.confirm(
                              `Delete "${entry.label || entry.id}" from the yarn library?\n\nThis removes the saved scan + metadata from disk. Already-imported project assets keep working.`,
                            );
                            if (ok) onDeleteFromLibrary(entry.id);
                          }}
                          disabled={isImporting}
                          data-testid={`yarn-library-delete-${entry.id}`}
                        >
                          🗑
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* The yarnseamless editor — full wizard-page area below the strip.
       *  Rendered without any card wrapper so its native layout / dark
       *  surfaces fill the page exactly like the standalone yarnseamless app.
       *
       *  Crucially, no max-height / overflow-hidden / framed container here.
       *  The editor's own <main className="flex-1 ... overflow-auto"> handles
       *  internal scrolling. */}
      <div className="ys-editor-host">
        {fragments.length === 0 ? (
          <MultiThreadImageEditor
            onAssembleDone={(frags: any[]) => setFragments(frags)}
            onCancel={() => { /* no parent-level cancel in wizard mode */ }}
          />
        ) : (
          <MultiFragmentEditor
            fragments={fragments}
            setFragments={setFragments}
            onAssembleDone={() => {
              /* MFE handles the post-assemble result view internally,
                 including the + Save to Library button. */
            }}
            onCancel={backToUpload}
            /* yarnseamless single-image-flow hook — wizard doesn't expose it. */
            onCropFragment={() => { /* no-op */ }}
            brushSize={brushSize}
            setBrushSize={setBrushSize}
          />
        )}
      </div>
    </section>
  );
}
