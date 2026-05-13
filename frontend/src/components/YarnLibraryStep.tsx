import { useMemo, useRef, useState } from 'react';
import type { YarnAsset } from '../domain/types';
import type { YarnOrientation } from '../utils/parserApi';

interface YarnLibraryStepProps {
  assets: YarnAsset[];
  busy: boolean;
  message: string;
  onUpload: (files: File[], orientation: YarnOrientation) => void;
  onRetry: (assetId: string, orientation: YarnOrientation) => void;
  onDelete: (assetId: string) => void;
  onRefresh: () => void;
}

function assetStatusLabel(status: YarnAsset['status']) {
  if (status === 'ready') {
    return 'Ready';
  }
  if (status === 'failed') {
    return 'Failed';
  }
  if (status === 'processing') {
    return 'Processing';
  }
  return 'Queued';
}

export default function YarnLibraryStep({
  assets,
  busy,
  message,
  onUpload,
  onRetry,
  onDelete,
  onRefresh,
}: YarnLibraryStepProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [orientation, setOrientation] = useState<YarnOrientation>('auto');
  const [search, setSearch] = useState('');

  const readyCount = assets.filter((asset) => asset.status === 'ready').length;
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return assets;
    return assets.filter((asset) => asset.label.toLowerCase().includes(q));
  }, [assets, search]);

  return (
    <section className="card fabric-step-card yarn-library" data-testid="yarn-library-step">
      <div className="fabric-step-card__header">
        <div>
          <p className="eyebrow">Step 1</p>
          <h2>Yarn Library</h2>
          <p className="fabric-step-card__summary">
            Upload yarns or pick a floating yarn — seamless textures are generated automatically.
          </p>
        </div>
        <div className="fabric-step-card__actions">
          <input
            type="search"
            className="yarn-library__search"
            placeholder="Search your yarn library…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            data-testid="yarn-search-input"
          />
          <label className="orientation-select">
            <span>Orientation</span>
            <select
              value={orientation}
              onChange={(event) => setOrientation(event.target.value as YarnOrientation)}
              disabled={busy}
              data-testid="yarn-orientation-select"
            >
              <option value="auto">Auto-detect</option>
              <option value="horizontal">Horizontal</option>
              <option value="vertical">Vertical</option>
            </select>
          </label>
          <button
            className="button button--accent"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            data-testid="yarn-upload-button"
          >
            {busy ? 'Uploading…' : 'Upload Yarn Images'}
          </button>
          <button className="button button--ghost" onClick={onRefresh} data-testid="yarn-refresh-button">
            Refresh Status
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        data-testid="yarn-upload-input"
        accept="image/*,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
        multiple
        onChange={(event) => {
          const files = Array.from(event.target.files || []);
          if (files.length) {
            onUpload(files, orientation);
          }
          event.target.value = '';
        }}
      />

      <div className="fabric-step-card__meta yarn-library__meta">
        <div className="status-pill status-pill--source">Assets: {assets.length}</div>
        <div className="status-pill status-pill--online">Ready: {readyCount}</div>
        <p className="muted">{message}</p>
      </div>

      {filtered.length ? (
        <div className="yarn-asset-grid">
          {filtered.map((asset) => (
            <article className="yarn-asset-card" key={asset.id} data-testid="yarn-asset-card">
              <div className="yarn-asset-card__header">
                <div>
                  <h3>{asset.label}</h3>
                  <p className={`status-pill status-pill--${asset.status === 'ready' ? 'online' : asset.status === 'failed' ? 'offline' : 'checking'}`}>
                    {assetStatusLabel(asset.status)}
                  </p>
                </div>
                <div className="yarn-asset-card__actions">
                  {asset.status === 'failed' ? (
                    <button className="button button--tiny" onClick={() => onRetry(asset.id, orientation)}>
                      Retry
                    </button>
                  ) : null}
                  <button className="button button--tiny button--ghost" onClick={() => onDelete(asset.id)}>
                    Delete
                  </button>
                </div>
              </div>

              <div className="yarn-asset-card__previews">
                <figure>
                  <span>Source</span>
                  <img src={asset.sourceUrl} alt={`${asset.label} source`} />
                </figure>
                <figure>
                  <span>Diffuse</span>
                  {asset.diffuseUrl ? (
                    <img src={asset.diffuseUrl} alt={`${asset.label} seamless diffuse`} />
                  ) : (
                    <div className="yarn-asset-card__placeholder">Waiting</div>
                  )}
                </figure>
                <figure>
                  <span>Alpha</span>
                  {asset.alphaUrl ? (
                    <img src={asset.alphaUrl} alt={`${asset.label} alpha`} />
                  ) : (
                    <div className="yarn-asset-card__placeholder">Waiting</div>
                  )}
                </figure>
              </div>

              {asset.error ? <p className="yarn-asset-card__error">{asset.error}</p> : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="fabric-empty-state" data-testid="yarn-empty-state">
          <strong>{search ? 'No yarns match your search' : 'No yarn assets yet'}</strong>
          <span>
            {search
              ? 'Try a different keyword, or clear the search to see your full library.'
              : 'Upload one or more yarn photos, or pick a floating yarn from the infiknit landing page.'}
          </span>
        </div>
      )}
    </section>
  );
}
