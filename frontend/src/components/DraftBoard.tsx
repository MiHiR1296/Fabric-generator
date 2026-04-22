import { useEffect, useRef } from 'react';
import { getReviewCell, getThreadingIndexFromDrawdownColumn } from '../domain/draft';
import type { DraftDocument, FocusedDrawdownCell } from '../domain/types';

interface DraftBoardProps {
  draft: DraftDocument;
  focus: FocusedDrawdownCell | null;
  activeColor: string;
  onThreadingSelect: (endIndex: number, shaft: number) => void;
  onTieUpToggle: (shaftIndex: number, treadleIndex: number, forcedValue?: boolean) => void;
  onTreadlingSelect: (pickIndex: number, treadle: number) => void;
  onWarpColorPaint: (endIndex: number, color: string) => void;
  onWeftColorPaint: (pickIndex: number, color: string) => void;
  onFocusCell: (cell: FocusedDrawdownCell | null) => void;
  onPinCell: (cell: FocusedDrawdownCell) => void;
  onResetSection: (section: 'threading' | 'tieUp' | 'treadling') => void;
}

type EditableSection = 'threading' | 'tieUp' | 'treadling' | 'warpColors' | 'weftColors';

interface DragPoint {
  row: number;
  col: number;
}

interface DragState {
  section: EditableSection;
  lastPoint: DragPoint;
  tieUpValue?: boolean;
  paintColor?: string;
}

function interpolateLine(start: DragPoint, end: DragPoint) {
  const points: DragPoint[] = [];
  let x0 = start.col;
  let y0 = start.row;
  const x1 = end.col;
  const y1 = end.row;
  const dx = Math.abs(x1 - x0);
  const dy = Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx - dy;

  while (true) {
    points.push({ row: y0, col: x0 });
    if (x0 === x1 && y0 === y1) {
      break;
    }
    const e2 = err * 2;
    if (e2 > -dy) {
      err -= dy;
      x0 += sx;
    }
    if (e2 < dx) {
      err += dx;
      y0 += sy;
    }
  }

  return points;
}

function getDrawdownFloatState(drawdown: number[][], pickIndex: number, endIndex: number) {
  const value = drawdown[pickIndex]?.[endIndex] ?? 0;

  if (value === 1) {
    return {
      value,
      joinUp: drawdown[pickIndex - 1]?.[endIndex] === 1,
      joinDown: drawdown[pickIndex + 1]?.[endIndex] === 1,
      joinLeft: false,
      joinRight: false,
    };
  }

  return {
    value,
    joinUp: false,
    joinDown: false,
    joinLeft: drawdown[pickIndex]?.[endIndex - 1] === 0,
    joinRight: drawdown[pickIndex]?.[endIndex + 1] === 0,
  };
}

function HelpHint({
  label,
  text,
}: {
  label: string;
  text: string;
}) {
  return (
    <span className="help-hint">
      <button type="button" className="help-hint__button" aria-label={label}>
        ?
      </button>
      <span className="help-hint__tooltip" role="tooltip">
        {text}
      </span>
    </span>
  );
}

function SectionHeading({
  title,
  helpText,
  onReset,
}: {
  title: string;
  helpText: string;
  onReset?: () => void;
}) {
  return (
    <div className="board-section__heading">
      <div className="board-section__title">
        <h2>{title}</h2>
        <HelpHint label={`Help for ${title}`} text={helpText} />
      </div>
      {onReset ? (
        <button className="button button--tiny" onClick={onReset}>
          Reset
        </button>
      ) : null}
    </div>
  );
}

function DraftControl({
  title,
  helpText,
  onReset,
}: {
  title: string;
  helpText: string;
  onReset?: () => void;
}) {
  return (
    <div className="draft-frame__control">
      <span className="draft-frame__control-label">{title}</span>
      <HelpHint label={`Help for ${title}`} text={helpText} />
      {onReset ? (
        <button className="button button--tiny" onClick={onReset}>
          Reset
        </button>
      ) : null}
    </div>
  );
}

export default function DraftBoard({
  draft,
  focus,
  activeColor,
  onThreadingSelect,
  onTieUpToggle,
  onTreadlingSelect,
  onWarpColorPaint,
  onWeftColorPaint,
  onFocusCell,
  onPinCell,
  onResetSection,
}: DraftBoardProps) {
  const dragStateRef = useRef<DragState | null>(null);
  const getThreadingIndex = (endIndex: number) =>
    getThreadingIndexFromDrawdownColumn(draft.threading.length, endIndex);
  const tieUpPath =
    focus == null
      ? null
      : {
          shaftIndex: draft.threading[getThreadingIndex(focus.endIndex)] - 1,
          treadleIndex: draft.treadling[focus.pickIndex] - 1,
        };

  useEffect(() => {
    const stopDragging = () => {
      dragStateRef.current = null;
    };

    window.addEventListener('mouseup', stopDragging);
    return () => {
      window.removeEventListener('mouseup', stopDragging);
    };
  }, []);

  const applyDragPoint = (
    section: EditableSection,
    point: DragPoint,
    forcedTieUpValue?: boolean,
    forcedPaintColor?: string,
  ) => {
    if (section === 'threading') {
      onThreadingSelect(getThreadingIndex(point.col), draft.shaftCount - point.row);
      return;
    }

    if (section === 'tieUp') {
      onTieUpToggle(draft.shaftCount - point.row - 1, point.col, forcedTieUpValue);
      return;
    }

    if (section === 'warpColors') {
      onWarpColorPaint(getThreadingIndex(point.col), forcedPaintColor || activeColor);
      return;
    }

    if (section === 'weftColors') {
      onWeftColorPaint(point.row, forcedPaintColor || activeColor);
      return;
    }

    onTreadlingSelect(point.row, point.col + 1);
  };

  const startDrag = (
    section: EditableSection,
    point: DragPoint,
    forcedTieUpValue?: boolean,
    forcedPaintColor?: string,
  ) => {
    dragStateRef.current = {
      section,
      lastPoint: point,
      tieUpValue: forcedTieUpValue,
      paintColor: forcedPaintColor,
    };
    applyDragPoint(section, point, forcedTieUpValue, forcedPaintColor);
  };

  const continueDrag = (section: EditableSection, point: DragPoint) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.section !== section) {
      return;
    }
    if (dragState.lastPoint.row === point.row && dragState.lastPoint.col === point.col) {
      return;
    }

    const points = interpolateLine(dragState.lastPoint, point);
    for (const linePoint of points.slice(1)) {
      applyDragPoint(section, linePoint, dragState.tieUpValue, dragState.paintColor);
    }
    dragStateRef.current = {
      ...dragState,
      lastPoint: point,
    };
  };

  return (
    <section className="board card board--unified" data-testid="draft-board">
      <div className="board__intro">
        <p className="eyebrow">Draft Workspace</p>
        <div className="board__title-row">
          <h2>Build the pattern</h2>
          <HelpHint
            label="Help for draft workspace"
            text="Tie-up sits in the top-right corner, threading runs to its left, treadling drops below it, and the color strips sit on the outer edges so the draft reads as one complete box."
          />
        </div>
      </div>

      <div className="draft-frame__controls" aria-label="Draft section controls">
        <DraftControl
          title="Threading"
          helpText="Each warp end belongs to one shaft. The first end starts at the tie-up corner on the right."
          onReset={() => onResetSection('threading')}
        />
        <DraftControl
          title="Tie-Up"
          helpText="A treadle lifts the shafts marked here. Click or drag to paint a straight line."
          onReset={() => onResetSection('tieUp')}
        />
        <DraftControl
          title="Drawdown"
          helpText="Read the woven result here. Hover or pin a cell to trace which shaft and treadle produced that crossing."
        />
        <DraftControl
          title="Treadling"
          helpText="Each pick selects one treadle. Click or drag to draw a treadling path."
          onReset={() => onResetSection('treadling')}
        />
      </div>

      <div className="draft-frame">
        <div className="draft-frame__warp-colors" data-testid="warp-colors-panel">
          <div className="grid grid--color-strip">
            <div className="grid__row">
              {Array.from({ length: draft.threading.length }).map((_, endIndex) => {
                const threadingIndex = getThreadingIndex(endIndex);
                const color = draft.warpColors[threadingIndex];
                const isFocused = focus?.endIndex === endIndex;
                return (
                  <button
                    key={`warp-color-${threadingIndex}`}
                    className={[
                      'cell',
                      'cell--color-strip',
                      isFocused ? 'cell--highlight' : '',
                    ].join(' ')}
                    style={{ backgroundColor: color }}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      startDrag('warpColors', { row: 0, col: endIndex }, undefined, activeColor);
                    }}
                    onMouseEnter={() => continueDrag('warpColors', { row: 0, col: endIndex })}
                    title={`Paint warp end ${threadingIndex + 1} with ${activeColor}`}
                  />
                );
              })}
            </div>
          </div>
        </div>

        <div
          className="draft-frame__paint-corner"
          title={`Active paint color ${activeColor}`}
          aria-label={`Active paint color ${activeColor}`}
        >
          <div className="grid grid--paint-corner">
            <div className="grid__row">
              <span
                className="cell cell--color-strip cell--paint-corner"
                style={{ backgroundColor: activeColor }}
                aria-hidden="true"
              />
            </div>
          </div>
        </div>

        <div className="draft-frame__threading board__panel" data-testid="threading-panel">
          <div className="grid grid--threading">
            {Array.from({ length: draft.shaftCount }).map((_, displayRow) => {
              const shaft = draft.shaftCount - displayRow;
              return (
                <div key={shaft} className="grid__row">
                  {Array.from({ length: draft.threading.length }).map((__, endIndex) => {
                    const threadingIndex = getThreadingIndex(endIndex);
                    const activeShaft = draft.threading[threadingIndex];
                    const reviewCell = getReviewCell(draft, 'threading', shaft - 1, threadingIndex);
                    const isActive = activeShaft === shaft;
                    const isFocused = focus?.endIndex === endIndex && activeShaft === shaft;
                    return (
                      <button
                        key={`${shaft}-${threadingIndex}`}
                        className={[
                          'cell',
                          isActive ? 'cell--filled' : '',
                          isFocused ? 'cell--highlight' : '',
                          reviewCell ? 'cell--review' : '',
                        ].join(' ')}
                        onMouseDown={(event) => {
                          event.preventDefault();
                          startDrag('threading', { row: displayRow, col: endIndex });
                        }}
                        onMouseEnter={() => continueDrag('threading', { row: displayRow, col: endIndex })}
                        title={
                          reviewCell
                            ? `${reviewCell.reason} (${Math.round(reviewCell.confidence * 100)}% confidence)`
                            : `Thread warp end ${threadingIndex + 1} on shaft ${shaft}`
                        }
                      />
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        <div className="draft-frame__tieup board__panel" data-testid="tieup-panel">
          <div className="grid grid--tieup">
            {Array.from({ length: draft.shaftCount }).map((_, displayRow) => {
              const shaft = draft.shaftCount - displayRow;
              return (
                <div key={shaft} className="grid__row">
                  {Array.from({ length: draft.treadleCount }).map((__, treadleIndex) => {
                    const value = draft.tieUp[shaft - 1]?.[treadleIndex];
                    const reviewCell = getReviewCell(draft, 'tieUp', shaft - 1, treadleIndex);
                    const isFocused =
                      tieUpPath?.shaftIndex === shaft - 1 && tieUpPath?.treadleIndex === treadleIndex;

                    return (
                      <button
                        key={`${shaft}-${treadleIndex}`}
                        className={[
                          'cell',
                          value ? 'cell--filled' : '',
                          isFocused ? 'cell--highlight' : '',
                          reviewCell ? 'cell--review' : '',
                        ].join(' ')}
                        onMouseDown={(event) => {
                          event.preventDefault();
                          startDrag(
                            'tieUp',
                            { row: displayRow, col: treadleIndex },
                            !value,
                          );
                        }}
                        onMouseEnter={() => continueDrag('tieUp', { row: displayRow, col: treadleIndex })}
                        title={
                          reviewCell
                            ? `${reviewCell.reason} (${Math.round(reviewCell.confidence * 100)}% confidence)`
                            : `Toggle shaft ${shaft} on treadle ${treadleIndex + 1}`
                        }
                      />
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        <div className="draft-frame__drawdown board__panel board__panel--drawdown" data-testid="drawdown-panel">
          <div className="grid grid--drawdown">
            {draft.drawdown.map((row, pickIndex) => (
              <div key={`drawdown-${pickIndex}`} className="grid__row">
                {row.map((value, endIndex) => {
                  const isFocused =
                    focus?.pickIndex === pickIndex && focus?.endIndex === endIndex;
                  const warpColor = draft.warpColors[getThreadingIndex(endIndex)];
                  const weftColor = draft.weftColors[pickIndex];
                  const floatState = getDrawdownFloatState(draft.drawdown, pickIndex, endIndex);
                  return (
                    <button
                      key={`${pickIndex}-${endIndex}`}
                      className={[
                        'cell',
                        'cell--drawdown',
                        value ? 'cell--warp' : 'cell--weft',
                        isFocused ? 'cell--highlight' : '',
                      ].join(' ')}
                      onMouseEnter={() => onFocusCell({ pickIndex, endIndex })}
                      onMouseLeave={() => onFocusCell(focus?.pinned ? focus : null)}
                      onClick={() => onPinCell({ pickIndex, endIndex, pinned: !isFocused || !focus?.pinned })}
                      title={value ? `Warp over: ${warpColor}` : `Weft over: ${weftColor}`}
                    >
                      <span
                        className={[
                          'drawdown-cell__strand',
                          'drawdown-cell__strand--warp',
                          floatState.joinUp ? 'drawdown-cell__strand--join-up' : '',
                          floatState.joinDown ? 'drawdown-cell__strand--join-down' : '',
                          value ? 'drawdown-cell__strand--top' : '',
                        ].join(' ')}
                        style={{ backgroundColor: warpColor }}
                        aria-hidden="true"
                      />
                      <span
                        className={[
                          'drawdown-cell__strand',
                          'drawdown-cell__strand--weft',
                          floatState.joinLeft ? 'drawdown-cell__strand--join-left' : '',
                          floatState.joinRight ? 'drawdown-cell__strand--join-right' : '',
                          value ? '' : 'drawdown-cell__strand--top',
                        ].join(' ')}
                        style={{ backgroundColor: weftColor }}
                        aria-hidden="true"
                      />
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="draft-frame__treadling board__panel" data-testid="treadling-panel">
          <div className="grid grid--treadling">
            {draft.treadling.map((activeTreadle, pickIndex) => (
              <div key={`pick-${pickIndex}`} className="grid__row">
                {Array.from({ length: draft.treadleCount }).map((_, treadleIndex) => {
                  const reviewCell = getReviewCell(draft, 'treadling', pickIndex, treadleIndex);
                  const isActive = activeTreadle === treadleIndex + 1;
                  const isFocused =
                    focus?.pickIndex === pickIndex && activeTreadle === treadleIndex + 1;
                  return (
                    <button
                      key={`${pickIndex}-${treadleIndex}`}
                      className={[
                        'cell',
                        isActive ? 'cell--filled' : '',
                        isFocused ? 'cell--highlight' : '',
                        reviewCell ? 'cell--review' : '',
                      ].join(' ')}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        startDrag('treadling', { row: pickIndex, col: treadleIndex });
                      }}
                      onMouseEnter={() => continueDrag('treadling', { row: pickIndex, col: treadleIndex })}
                      title={
                        reviewCell
                          ? `${reviewCell.reason} (${Math.round(reviewCell.confidence * 100)}% confidence)`
                          : `Use treadle ${treadleIndex + 1} on pick ${pickIndex + 1}`
                      }
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="draft-frame__weft-colors" data-testid="weft-colors-panel">
          <div className="grid grid--weft-color-strip">
            {draft.weftColors.map((color, pickIndex) => {
              const isFocused = focus?.pickIndex === pickIndex;
              return (
                <div key={`weft-color-${pickIndex}`} className="grid__row">
                  <button
                    className={[
                      'cell',
                      'cell--color-strip',
                      isFocused ? 'cell--highlight' : '',
                    ].join(' ')}
                    style={{ backgroundColor: color }}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      startDrag('weftColors', { row: pickIndex, col: 0 }, undefined, activeColor);
                    }}
                    onMouseEnter={() => continueDrag('weftColors', { row: pickIndex, col: 0 })}
                    title={`Paint pick ${pickIndex + 1} with ${activeColor}`}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
