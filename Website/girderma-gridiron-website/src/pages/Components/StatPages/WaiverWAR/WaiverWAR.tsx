import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';

import './WaiverWAR.css';
import './WaiverWARExtras.css';

interface WaiverEntry {
  Player: string;
  'Player ID': string;
  Position: string;
  Team: string;
  'Team Key': string;
  Manager: string;
  'Weeks Rostered': number[];
  WAR: number;
  'WAR Rank': number;
}

// ---------- Zoomable image ----------

const MIN_SCALE = 1;
const MAX_SCALE = 8;
const BUTTON_STEP = 1.4;

interface View {
  scale: number;
  x: number;
  y: number;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

const ZoomableImage: React.FC<{ src: string; alt: string }> = ({ src, alt }) => {
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragStart = useRef<{ px: number; py: number; x: number; y: number } | null>(null);

  // Zoom toward a point (cx, cy) measured from the viewport's top-left.
  const zoomAt = useCallback((factor: number, cx: number, cy: number) => {
    setView((v) => {
      const next = clamp(v.scale * factor, MIN_SCALE, MAX_SCALE);
      if (next === v.scale) return v;
      const ratio = next / v.scale;
      if (next === MIN_SCALE) return { scale: 1, x: 0, y: 0 };
      return { scale: next, x: cx - (cx - v.x) * ratio, y: cy - (cy - v.y) * ratio };
    });
  }, []);

  const zoomFromCenter = (factor: number) => {
    const el = viewportRef.current;
    if (!el) return;
    zoomAt(factor, el.clientWidth / 2, el.clientHeight / 2);
  };

  // Native wheel listener so we can preventDefault (React's onWheel is passive).
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * 0.0015);
      zoomAt(factor, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (view.scale === 1) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragStart.current = { px: e.clientX, py: e.clientY, x: view.x, y: view.y };
    setDragging(true);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const start = dragStart.current;
    if (!start) return;
    setView((v) => ({
      ...v,
      x: start.x + (e.clientX - start.px),
      y: start.y + (e.clientY - start.py),
    }));
  };

  const endDrag = () => {
    dragStart.current = null;
    setDragging(false);
  };

  const reset = () => setView({ scale: 1, x: 0, y: 0 });

  const onDoubleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    if (view.scale > 1) reset();
    else zoomAt(2.5, e.clientX - rect.left, e.clientY - rect.top);
  };

  return (
    <div className="waiver-war__zoom">
      <div className="waiver-war__zoom-controls" role="group" aria-label="Zoom controls">
        <button type="button" onClick={() => zoomFromCenter(1 / BUTTON_STEP)} aria-label="Zoom out" disabled={view.scale <= MIN_SCALE}>
          <Minus size={16} strokeWidth={1.5} />
        </button>
        <span className="waiver-war__zoom-level">{Math.round(view.scale * 100)}%</span>
        <button type="button" onClick={() => zoomFromCenter(BUTTON_STEP)} aria-label="Zoom in" disabled={view.scale >= MAX_SCALE}>
          <Plus size={16} strokeWidth={1.5} />
        </button>
        <button type="button" onClick={reset} aria-label="Reset zoom" disabled={view.scale === 1}>
          <RotateCcw size={16} strokeWidth={1.5} />
        </button>
      </div>

      <div
        ref={viewportRef}
        className={`waiver-war__zoom-viewport${view.scale > 1 ? ' is-zoomed' : ''}${dragging ? ' is-dragging' : ''}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={onDoubleClick}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
        />
      </div>
      <p className="waiver-war__zoom-hint">Scroll to zoom, drag to pan, double-click to toggle zoom.</p>
    </div>
  );
};

// ---------- Leaderboard ----------

const formatWar = (war: number) => (war > 0 ? `+${war.toFixed(3)}` : war.toFixed(3));

const formatWeeks = (weeks: number[]) => {
  if (weeks.length === 0) return '';
  const sorted = [...weeks].sort((a, b) => a - b);
  const ranges: string[] = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (let i = 1; i <= sorted.length; i++) {
    const cur = sorted[i];
    if (cur !== prev + 1) {
      ranges.push(start === prev ? `${start}` : `${start}–${prev}`);
      start = cur;
    }
    prev = cur;
  }
  return `Weeks ${ranges.join(', ')}`;
};

const Leaderboard: React.FC<{ waiverData: WaiverEntry[] }> = ({ waiverData }) => {
  const [position, setPosition] = useState<string>('ALL');

  const sorted = useMemo(
    () => [...waiverData].sort((a, b) => b.WAR - a.WAR),
    [waiverData],
  );

  const positions = useMemo(() => {
    const order = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'];
    const present = new Set(sorted.map((e) => e.Position));
    return ['ALL', ...order.filter((p) => present.has(p))];
  }, [sorted]);

  const rows = useMemo(
    () => (position === 'ALL' ? sorted : sorted.filter((e) => e.Position === position)),
    [sorted, position],
  );

  if (sorted.length === 0) {
    return <p className="waiver-war__empty">No waiver data available.</p>;
  }

  return (
    <div className="waiver-war__board">
      <div className="waiver-war__filters" role="group" aria-label="Filter by position">
        {positions.map((p) => (
          <button
            key={p}
            type="button"
            className={p === position ? 'is-active' : ''}
            onClick={() => setPosition(p)}
          >
            {p === 'ALL' ? 'All positions' : p}
          </button>
        ))}
      </div>

      <div className="waiver-war__table-wrap">
        <table className="waiver-war__table">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Player</th>
              <th>Manager</th>
              <th className="num">Weeks rostered</th>
              <th className="num">WAR</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={`${e['Player ID']}-${e['Team Key']}`}>
                <td className="num">{i + 1}</td>
                <td>
                  <span className="waiver-war__player">{e.Player}</span>
                  <span className="waiver-war__pos">{e.Position}</span>
                </td>
                <td>
                  {e.Manager}
                  <span className="waiver-war__team">{e.Team}</span>
                </td>
                <td className="num" title={formatWeeks(e['Weeks Rostered'])}>
                  {e['Weeks Rostered'].length}
                </td>
                <td className={`num waiver-war__war ${e.WAR > 0 ? 'is-pos' : e.WAR < 0 ? 'is-neg' : ''}`}>
                  {formatWar(e.WAR)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ---------- Page ----------

type Mode = 'image' | 'leaderboard';

interface WaiverWARProps {
  year: number | string;
}

const WaiverWAR: React.FC<WaiverWARProps> = ({ year }) => {
  const [mode, setMode] = useState<Mode>('image');
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [secondImageSrc, setSecondImageSrc] = useState<string | null>(null);
  const [waiverData, setWaiverData] = useState<WaiverEntry[]>([]);

  // Load both images and the data for the requested year whenever it changes
  useEffect(() => {
    let cancelled = false;
    setImageSrc(null);
    setSecondImageSrc(null);
    setWaiverData([]);

    import(
      `../../../../league_stats_output/${year}/WaiverWar/waiver_war_board_${year}.png`
    )
      .then((module) => {
        if (cancelled) return;
        setImageSrc(module.default as string);
      })
      .catch(() => {
        if (cancelled) return;
        setImageSrc(null);
      });

    import(
      `../../../../league_stats_output/${year}/WaiverWar/waiver_war_board_${year}_colorbar.png`
    )
      .then((module) => {
        if (cancelled) return;
        setSecondImageSrc(module.default as string);
      })
      .catch(() => {
        if (cancelled) return;
        setSecondImageSrc(null);
      });

    import(`../../../../league_stats_output/${year}/WaiverWar.json`)
      .then((module) => {
        if (cancelled) return;
        setWaiverData((module.default ?? module) as WaiverEntry[]);
      })
      .catch(() => {
        if (cancelled) return;
        setWaiverData([]);
      });

    return () => {
      cancelled = true;
    };
  }, [year]);

  return (
    <div className="draft-board-page waiver-war">
      <header className="waiver-war__header">
        <div>
          <h2 className="waiver-war__title">Waiver WAR</h2>
          <p className="waiver-war__desc">WAR for all waiver players.</p>
        </div>

        <div className="waiver-war__modes" role="tablist" aria-label="View mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'image'}
            className={mode === 'image' ? 'is-active' : ''}
            onClick={() => setMode('image')}
          >
            Board
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'leaderboard'}
            className={mode === 'leaderboard' ? 'is-active' : ''}
            onClick={() => setMode('leaderboard')}
          >
            Leaderboard
          </button>
        </div>
      </header>

      {mode === 'image' ? (
        <>
          {imageSrc ? (
            <ZoomableImage key={imageSrc} src={imageSrc} alt="Waiver WAR board" />
          ) : (
            <p className="waiver-war__empty">No chart available.</p>
          )}

          {secondImageSrc && (
            <div className="draft-board-page__colorbar">
              <img src={secondImageSrc} alt="Waiver WAR board color scale" />
            </div>
          )}
        </>
      ) : (
        <Leaderboard waiverData={waiverData} />
      )}
    </div>
  );
};

export default WaiverWAR;