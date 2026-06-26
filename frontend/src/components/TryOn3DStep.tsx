import { useEffect, useMemo, useRef, useState } from 'react';
import type { BlenderRenderJob, TryonTarget } from '../domain/types';
import { fetchDraftRenderJob, listTryonTargets, requestTryonRender } from '../utils/parserApi';

interface TryOn3DStepProps {
  // The flat Blender render preview from Step 3.
  renderJob: BlenderRenderJob | null;
  // The seam-repaired seamless tile from Step 3 (preferred drape texture).
  tileJob: BlenderRenderJob | null;
}

interface GalleryEntry {
  jobId: string;
  targetId: string;
  label: string;
  job: BlenderRenderJob | null;
}

const TERMINAL = new Set(['succeeded', 'failed']);

function isUsableSource(job: BlenderRenderJob | null): job is BlenderRenderJob {
  return Boolean(job && job.status === 'succeeded' && job.imageUrl);
}

export default function TryOn3DStep({ renderJob, tileJob }: TryOn3DStepProps) {
  const [targets, setTargets] = useState<TryonTarget[]>([]);
  const [blendFileExists, setBlendFileExists] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [entries, setEntries] = useState<GalleryEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Pick one or more objects, then render your fabric onto them.');
  const pollRef = useRef<number | null>(null);

  // Prefer the seamless tile (designed to tile across a surface); fall back to
  // the flat render preview. The backend only needs the source job id.
  const source = useMemo(() => {
    if (isUsableSource(tileJob)) return { job: tileJob, label: 'seamless tile' };
    if (isUsableSource(renderJob)) return { job: renderJob, label: 'render preview' };
    return null;
  }, [tileJob, renderJob]);

  useEffect(() => {
    let cancelled = false;
    listTryonTargets()
      .then((data) => {
        if (cancelled) return;
        setTargets(data.targets || []);
        setBlendFileExists(Boolean(data.blendFileExists));
        // Default-select the first target for a one-click first render.
        setSelected((current) => {
          if (current.size > 0 || !data.targets?.length) return current;
          return new Set([data.targets[0].id]);
        });
      })
      .catch((error) => {
        if (cancelled) return;
        setMessage(error instanceof Error ? error.message : 'Unable to load the object list.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll any non-terminal jobs in the gallery until all settle.
  useEffect(() => {
    const pending = entries.filter((entry) => !entry.job || !TERMINAL.has(entry.job.status));
    if (pending.length === 0) {
      if (pollRef.current) {
        window.clearTimeout(pollRef.current);
        pollRef.current = null;
      }
      return undefined;
    }
    pollRef.current = window.setTimeout(async () => {
      const updates = await Promise.all(
        pending.map(async (entry) => {
          try {
            return { jobId: entry.jobId, job: await fetchDraftRenderJob(entry.jobId) };
          } catch {
            return null;
          }
        }),
      );
      const byId = new Map(updates.filter(Boolean).map((u) => [u!.jobId, u!.job]));
      setEntries((current) =>
        current.map((entry) => (byId.has(entry.jobId) ? { ...entry, job: byId.get(entry.jobId)! } : entry)),
      );
    }, 1500);
    return () => {
      if (pollRef.current) {
        window.clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [entries]);

  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleRender = async () => {
    if (!source || selected.size === 0) return;
    setBusy(true);
    // Render in catalog order so the gallery is stable.
    const orderedIds = targets.filter((t) => selected.has(t.id)).map((t) => t.id);
    try {
      const batch = await requestTryonRender(orderedIds, source.job.id);
      setEntries(
        batch.jobs.map((ref) => ({
          jobId: ref.jobId,
          targetId: ref.targetId,
          label: ref.label,
          job: null,
        })),
      );
      setMessage(
        `Rendering ${batch.jobs.length} object${batch.jobs.length === 1 ? '' : 's'} one at a time. Each appears here as it finishes.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to start the Try-On render.');
    } finally {
      setBusy(false);
    }
  };

  const doneCount = entries.filter((e) => e.job?.status === 'succeeded').length;
  const activeCount = entries.filter((e) => e.job && e.job.status === 'running').length;
  const allDone = entries.length > 0 && entries.every((e) => e.job && TERMINAL.has(e.job.status));

  return (
    <section className="fabric-step-panel" data-testid="try-on-3d-step">
      <section className="card fabric-step-card">
        <div className="fabric-step-card__header">
          <div>
            <p className="eyebrow">Step 4 · Try On 3D</p>
            <h2>Drape your fabric onto real 3D objects</h2>
            <p className="fabric-step-card__summary">
              Pick the objects you want to see your fabric on, then render. Blender renders them one
              at a time and the results show up below as each finishes.
            </p>
          </div>
        </div>

        {!source ? (
          <p className="muted" data-testid="try-on-3d-no-source">
            No fabric texture yet. Go to <strong>Step 3 · Render Preview</strong> and run a render (or
            build a seamless tile), then come back here.
          </p>
        ) : !blendFileExists ? (
          <p className="muted">
            The 3D object scene (<code>Renders/Objects.blend</code>) wasn’t found on the backend.
          </p>
        ) : (
          <>
            <div className="try-on-3d__source" style={{ display: 'flex', gap: 14, alignItems: 'center', margin: '8px 0 18px' }}>
              <img
                src={source.job.imageUrl as string}
                alt="Fabric texture"
                style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)' }}
              />
              <div className="muted" style={{ fontSize: 13 }}>
                Using your <strong>{source.label}</strong> as the fabric. This is what gets draped onto
                each object you select.
              </div>
            </div>

            <fieldset
              className="try-on-3d__targets"
              style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: 14, marginBottom: 16 }}
            >
              <legend style={{ padding: '0 8px', fontSize: 13 }}>Objects to render</legend>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
                {targets.map((target) => (
                  <label
                    key={target.id}
                    className="try-on-3d__target"
                    data-testid={`try-on-3d-target-${target.id}`}
                    style={{
                      display: 'flex',
                      gap: 10,
                      alignItems: 'flex-start',
                      padding: 12,
                      borderRadius: 10,
                      cursor: 'pointer',
                      background: selected.has(target.id) ? 'rgba(120,150,255,0.12)' : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${selected.has(target.id) ? 'rgba(120,150,255,0.5)' : 'rgba(255,255,255,0.08)'}`,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(target.id)}
                      onChange={() => toggle(target.id)}
                      style={{ marginTop: 3 }}
                    />
                    <span>
                      <span style={{ display: 'block', fontWeight: 600 }}>{target.label}</span>
                      <span className="muted" style={{ fontSize: 12 }}>{target.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="primary"
                onClick={handleRender}
                disabled={busy || selected.size === 0}
                data-testid="try-on-3d-render"
              >
                {busy ? 'Starting…' : `Render ${selected.size || ''} object${selected.size === 1 ? '' : 's'}`.trim()}
              </button>
              {entries.length > 0 && (
                <span className="muted" style={{ fontSize: 13 }}>
                  {allDone
                    ? `Done — ${doneCount}/${entries.length} rendered.`
                    : `${doneCount}/${entries.length} done${activeCount ? ', 1 rendering…' : ', queued…'}`}
                </span>
              )}
            </div>
          </>
        )}

        <p className="muted" style={{ marginTop: 12 }}>{message}</p>

        {entries.length > 0 && (
          <div
            className="try-on-3d__gallery"
            data-testid="try-on-3d-gallery"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginTop: 18 }}
          >
            {entries.map((entry) => {
              const status = entry.job?.status || 'queued';
              const done = status === 'succeeded';
              const failed = status === 'failed';
              return (
                <figure
                  key={entry.jobId}
                  data-testid={`try-on-3d-result-${entry.targetId}`}
                  style={{ margin: 0, borderRadius: 12, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)', background: '#23232a' }}
                >
                  <div
                    style={{
                      aspectRatio: '1 / 1',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: '#2c2c34',
                      backgroundImage:
                        'linear-gradient(45deg, #2a2a31 25%, transparent 25%), linear-gradient(-45deg, #2a2a31 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #2a2a31 75%), linear-gradient(-45deg, transparent 75%, #2a2a31 75%)',
                      backgroundSize: '20px 20px',
                      backgroundPosition: '0 0, 0 10px, 10px -10px, -10px 0px',
                    }}
                  >
                    {done && entry.job?.imageUrl ? (
                      <img
                        src={entry.job.imageUrl}
                        alt={entry.label}
                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                      />
                    ) : (
                      <span className="muted" style={{ fontSize: 13, textAlign: 'center', padding: 16 }}>
                        {failed ? '⚠ Render failed' : status === 'running' ? 'Rendering…' : 'Queued…'}
                      </span>
                    )}
                  </div>
                  <figcaption style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px' }}>
                    <span style={{ fontWeight: 600 }}>{entry.label}</span>
                    <span
                      className="muted"
                      style={{ fontSize: 12, color: failed ? '#e08a8a' : done ? '#8ad6a0' : undefined }}
                    >
                      {status}
                    </span>
                  </figcaption>
                  {failed && entry.job?.message ? (
                    <p className="muted" style={{ fontSize: 11, padding: '0 12px 12px', margin: 0 }}>
                      {entry.job.message}
                    </p>
                  ) : null}
                </figure>
              );
            })}
          </div>
        )}
      </section>
    </section>
  );
}
