import { useRef } from 'react';
import type { YarnAsset } from '../domain/types';

interface YarnLibraryStepProps {
  assets: YarnAsset[];
  busy: boolean;
  message: string;
  onUpload: (files: File[]) => void;
  onRetry: (assetId: string) => void;
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
  const readyCount = assets.filter((asset) => asset.status === 'ready').length;

  return (
    <section className="card fabric-step-card yarn-library" data-testid="yarn-library-step">
      <div className="fabric-step-card__header">
        <div>
          <p className="eyebrow">Step 1</p>
          <h2>Yarn Library</h2>
          <p className="fabric-step-card__summary">
            Upload yarn images and let the backend generate seamless diffuse and alpha maps in the background.
          </p>
        </div>
        <div className="fabric-step-card__actions">
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
            onUpload(files);
          }
          event.target.value = '';
        }}
      />

      <div className="fabric-step-card__meta">
        <div className="status-pill status-pill--source">Assets: {assets.length}</div>
        <div className="status-pill status-pill--online">Ready: {readyCount}</div>
        <p className="muted">{message}</p>
      </div>

      {assets.length ? (
        <div className="yarn-asset-grid">
          {assets.map((asset) => (
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
                    <button className="button button--tiny" onClick={() => onRetry(asset.id)}>
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
          <strong>No yarn assets yet</strong>
          <span>Upload one or more yarn photos to start building the material library for this project.</span>
        </div>
      )}
    </section>
  );
}
