import { useEffect, useMemo, useState } from "react";
import rawData from "../../league_stats_output/All/PlayerTimelines.json";
import "./PlayerAnalysis.css";

/* ---------- Types ---------- */

type EventType = "drafted" | "added" | "dropped" | "traded";

interface TimelineEvent {
  type: EventType;
  year: number;
  phase: "draft" | "preseason" | "regular_season";
  week: number | null;
  date: string | null;
  team: string;
  manager: string;
  round?: number;
  pick?: number;
  source?: string;
  destination?: string;
  from_team?: string;
  from_manager?: string;
}

interface Player {
  player_id: string;
  name: string;
  position: string;
  seasons: number[];
  timeline: TimelineEvent[];
}

interface Data {
  years: number[];
  players: Record<string, Player>;
}

const data = rawData as unknown as Data;

/* ---------- Helpers ---------- */

const slugify = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const ALL_PLAYERS = Object.values(data.players).sort((a, b) =>
  a.name.localeCompare(b.name)
);

const BY_ID = data.players;
const BY_SLUG = new Map(ALL_PLAYERS.map((p) => [slugify(p.name), p]));

/** Accepts a slug ("justin-jefferson"), a raw name, or a player id. */
function resolvePlayer(param: string | null): Player | null {
  if (!param) return null;
  return BY_ID[param] ?? BY_SLUG.get(slugify(param)) ?? null;
}

function readParam(): string | null {
  return new URLSearchParams(window.location.search).get("player");
}

function writeParam(player: Player | null) {
  const url = new URL(window.location.href);
  if (player) url.searchParams.set("player", slugify(player.name));
  else url.searchParams.delete("player");
  window.history.pushState({}, "", url);
}

const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";

function sortEvents(events: TimelineEvent[]) {
  return [...events].sort((a, b) => {
    if (a.type === "drafted") return -1;
    if (b.type === "drafted") return 1;
    return (a.date ?? "").localeCompare(b.date ?? "");
  });
}

function phaseLabel(e: TimelineEvent) {
  if (e.type === "drafted") return "Draft";
  if (e.phase === "preseason") return "Preseason";
  return e.week ? `Week ${e.week}` : "Season";
}

const SOURCE_LABEL: Record<string, string> = {
  waivers: "waivers",
  freeagents: "free agency",
};

function describe(e: TimelineEvent) {
  switch (e.type) {
    case "drafted":
      return (
        <>
          Drafted by <strong>{e.manager}</strong> in round {e.round}, pick{" "}
          {e.pick}
        </>
      );
    case "added":
      return (
        <>
          Picked up by <strong>{e.manager}</strong> from{" "}
          {SOURCE_LABEL[e.source ?? ""] ?? e.source}
        </>
      );
    case "dropped":
      return (
        <>
          Dropped by <strong>{e.manager}</strong> to{" "}
          {SOURCE_LABEL[e.destination ?? ""] ?? e.destination}
        </>
      );
    case "traded":
      return (
        <>
          Traded from <strong>{e.from_manager}</strong> to{" "}
          <strong>{e.manager}</strong>
        </>
      );
  }
}

/* ---------- Components ---------- */

function Event({ e }: { e: TimelineEvent }) {
  return (
    <li className={`event event--${e.type}`}>
      <span className="event__dot" aria-hidden="true" />
      <div className="event__body">
        <div className="event__head">
          <span className="badge">{e.type}</span>
          <span className="event__when">{phaseLabel(e)}</span>
          {e.date && <span className="event__date">{fmtDate(e.date)}</span>}
        </div>
        <p className="event__text">{describe(e)}</p>
        <p className="event__team">
          {e.type === "traded" && e.from_team ? `${e.from_team} → ` : ""}
          {e.team}
        </p>
      </div>
    </li>
  );
}

function PlayerDetail({ player, onBack }: { player: Player; onBack: () => void }) {
  const [copied, setCopied] = useState(false);

  const years = useMemo(() => {
    const groups = new Map<number, TimelineEvent[]>();
    for (const e of player.timeline) {
      groups.set(e.year, [...(groups.get(e.year) ?? []), e]);
    }
    return Array.from(groups.entries())
        .sort((a, b) => a[0] - b[0])
      .map(([year, events]) => ({ year, events: sortEvents(events) }));
  }, [player]);

  const stats = useMemo(() => {
    const count = (t: EventType) =>
      player.timeline.filter((e) => e.type === t).length;
    const drafts = player.timeline.filter((e) => e.type === "drafted");
    const best = drafts.reduce<TimelineEvent | null>(
      (m, e) => (!m || (e.round ?? 99) * 1000 + (e.pick ?? 0) < (m.round ?? 99) * 1000 + (m.pick ?? 0) ? e : m),
      null
    );
    const managers = new Set(player.timeline.map((e) => e.manager));
    return {
      drafted: count("drafted"),
      trades: count("traded"),
      moves: count("added") + count("dropped"),
      managers: managers.size,
      best,
    };
  }, [player]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <article className="detail">
      <button className="link-btn" onClick={onBack}>
        ← All players
      </button>

      <header className="detail__header">
        <div>
          <span className={`pos pos--${player.position}`}>{player.position}</span>
          <h1 className="detail__name">{player.name}</h1>
          <p className="detail__seasons">
            Seasons: {player.seasons.join(", ")}
          </p>
        </div>
        <button className="btn" onClick={copyLink}>
          {copied ? "Link copied" : "Copy link"}
        </button>
      </header>

      <dl className="stats">
        <div>
          <dt>Times drafted</dt>
          <dd>{stats.drafted}</dd>
        </div>
        <div>
          <dt>Trades</dt>
          <dd>{stats.trades}</dd>
        </div>
        <div>
          <dt>Adds and drops</dt>
          <dd>{stats.moves}</dd>
        </div>
        <div>
          <dt>Managers</dt>
          <dd>{stats.managers}</dd>
        </div>
        {stats.best && (
          <div>
            <dt>Earliest pick</dt>
            <dd>
              {stats.best.year} · R{stats.best.round} #{stats.best.pick}
            </dd>
          </div>
        )}
      </dl>

      {years.map(({ year, events }) => (
        <section key={year} className="year">
          <h2 className="year__title">{year}</h2>
          <ol className="events">
            {events.map((e, i) => (
              <Event key={`${e.type}-${e.date}-${i}`} e={e} />
            ))}
          </ol>
        </section>
      ))}
    </article>
  );
}

function lastManager(p: Player) {
  const last = sortEvents(
    p.timeline.filter((e) => e.year === Math.max(...p.timeline.map((x) => x.year)))
  ).at(-1);
  return last?.type === "dropped" ? "Free agent" : last?.manager ?? "—";
}

const POSITIONS = ["All", "QB", "RB", "WR", "TE", "K", "DEF"];
const LIMIT = 60;

export default function PlayerHistory() {
  const [selected, setSelected] = useState<Player | null>(() =>
    resolvePlayer(readParam())
  );
  const [missing, setMissing] = useState<string | null>(() => {
    const p = readParam();
    return p && !resolvePlayer(p) ? p : null;
  });
  const [query, setQuery] = useState(() => (readParam() && !resolvePlayer(readParam()) ? readParam()! : ""));
  const [pos, setPos] = useState("All");

  // Keep in sync with back/forward navigation and manually edited URLs.
  useEffect(() => {
    const onPop = () => {
      const param = readParam();
      const p = resolvePlayer(param);
      setSelected(p);
      setMissing(param && !p ? param : null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    document.title = selected ? `${selected.name} · Player history` : "Player history";
  }, [selected]);

  const open = (p: Player | null) => {
    setSelected(p);
    setMissing(null);
    writeParam(p);
    window.scrollTo({ top: 0 });
  };

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    return ALL_PLAYERS.filter(
      (p) =>
        (pos === "All" || p.position === pos) &&
        (!q || p.name.toLowerCase().includes(q))
    );
  }, [query, pos]);

  if (selected) {
    return (
      <main className="page">
        <PlayerDetail player={selected} onBack={() => open(null)} />
      </main>
    );
  }

  return (
    <main className="page">
      <header className="intro">
        <h1 className="intro__title">Player history</h1>
        <p className="intro__sub">
          Every draft pick, trade, add and drop across {data.years.join(", ")}.
          Search for a player to see where they have been.
        </p>
      </header>

      {missing && (
        <p className="notice" role="status">
          No player matches “{missing}”. Try searching by name below.
        </p>
      )}

      <div className="controls">
        <input
          type="search"
          className="search"
          placeholder="Search players by name"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search players"
          autoFocus
        />
        <div className="chips" role="group" aria-label="Filter by position">
          {POSITIONS.map((p) => (
            <button
              key={p}
              className={`chip${pos === p ? " chip--on" : ""}`}
              aria-pressed={pos === p}
              onClick={() => setPos(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <p className="count">
        {results.length} player{results.length === 1 ? "" : "s"}
        {results.length > LIMIT && ` · showing first ${LIMIT}, search to narrow`}
      </p>

      {results.length === 0 ? (
        <p className="empty">No players found. Check the spelling or clear the position filter.</p>
      ) : (
        <ul className="grid">
          {results.slice(0, LIMIT).map((p) => (
            <li key={p.player_id}>
              <button className="card" onClick={() => open(p)}>
                <span className={`pos pos--${p.position}`}>{p.position}</span>
                <span className="card__name">{p.name}</span>
                <span className="card__meta">
                  {p.timeline.length} events · now {lastManager(p)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
