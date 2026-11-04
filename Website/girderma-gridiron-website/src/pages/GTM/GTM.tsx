import { useState } from "react";
import "./GTM.css";

/* ---------- Data ---------- */
import data2023 from "../../league_stats_output/GTM/2023.json";
import data2024 from "../../league_stats_output/GTM/2024.json";
import data2025 from "../../league_stats_output/GTM/2025.json";
import data2026 from "../../league_stats_output/GTM/2026.json";

/* ---------- Config ---------- */
const DATA_BY_YEAR: Record<number, PlayerEntry[]> = {
  2023: data2023 as PlayerEntry[],
  2024: data2024 as PlayerEntry[],
  2025: data2025 as PlayerEntry[],
  2026: data2026 as PlayerEntry[],
};

const YEARS = Object.keys(DATA_BY_YEAR)
  .map(Number)
  .sort((a, b) => b - a);

const QUESTION_COUNT = 20;

interface Pool {
  id: string;
  label: string;
  blurb: string;
  years: number[];
}

// One button per season.
const SINGLE_POOLS: Pool[] = YEARS.map((y) => ({ id: String(y), label: String(y), blurb: "", years: [y] }));

// Multi-season modes. Each question shows its year so you know which league it's from.
const MULTI_POOLS: Pool[] = [
  { id: "all", label: "All seasons", blurb: "Every year mixed together", years: [...YEARS] },
  { id: "12", label: "2023–2024", blurb: "12-manager era", years: YEARS.filter((y) => y <= 2024) },
  { id: "14", label: "2025+", blurb: "14-manager era", years: YEARS.filter((y) => y >= 2025) },
];

// Answer buttons only list managers who were in the league that year.
const MANAGERS_BY_YEAR: Record<number, string[]> = Object.fromEntries(
  YEARS.map((y) => [
    y,
    Array.from(new Set(DATA_BY_YEAR[y].map((p) => p.manager))).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" })
    ),
  ])
);

type Difficulty = "easy" | "medium" | "hard" | "impossible";

interface Level {
  id: Difficulty;
  label: string;
  blurb: string;
  min: number;
  max: number;
}

// Ranges overlap on purpose. Inside a range, players near the middle show up
// most often and players near the edges show up least (a bell curve).
const LEVELS: Level[] = [
  { id: "easy", label: "Easy", blurb: "Household names", min: 0, max: 40 },
  { id: "medium", label: "Medium", blurb: "Starters", min: 30, max: 70 },
  { id: "hard", label: "Hard", blurb: "Starters and Bench Players", min: 40, max: 90 },
  { id: "impossible", label: "Impossible", blurb: "Impossibly hard", min: 60, max: 100 },
];

/* ---------- Types ---------- */
interface PlayerEntry {
  player_id: string;
  player_name: string;
  manager: string;
  year: number;
  difficulty: number;
}

interface Answer {
  player: PlayerEntry;
  picked: string;
}

type Phase = "select" | "playing" | "done";

/* ---------- Helpers ---------- */
function shuffle<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

// Picks `count` players without repeats. Each player's chance depends on how
// close their difficulty is to the middle of the level's range.
function weightedSample<T>(items: T[], weightOf: (item: T) => number, count: number): T[] {
  return items
    .map((item) => ({ item, key: Math.log(Math.random()) / weightOf(item) }))
    .sort((a, b) => b.key - a.key)
    .slice(0, count)
    .map((x) => x.item);
}

function pickQuestions(data: PlayerEntry[], level: Level, count: number): PlayerEntry[] {
  const center = (level.min + level.max) / 2;
  const sigma = (level.max - level.min) / 4; // edges are ~13% as likely as the middle
  const weight = (p: PlayerEntry) => Math.exp(-((p.difficulty - center) ** 2) / (2 * sigma ** 2));

  const inRange = data.filter((p) => p.difficulty >= level.min && p.difficulty <= level.max);
  const picked = weightedSample(inRange, weight, count);

  // If a year has too few players in range, fill with the closest remaining ones.
  if (picked.length < count) {
    const chosen = new Set(picked);
    const rest = data
      .filter((p) => !chosen.has(p))
      .sort((a, b) => Math.abs(a.difficulty - center) - Math.abs(b.difficulty - center));
    picked.push(...rest.slice(0, count - picked.length));
  }

  return shuffle(picked);
}

function verdict(score: number, total: number): string {
  const pct = total === 0 ? 0 : score / total;
  if (pct === 1) return "Perfect. You know this league.";
  if (pct >= 0.75) return "Commissioner material.";
  if (pct >= 0.5) return "Solid. You were paying attention.";
  if (pct >= 0.25) return "Guess you weren't paying attention.";
  return "Did you even join this league?";
}

/* ---------- Component ---------- */
export default function ManagerGame() {
  const [phase, setPhase] = useState<Phase>("select");
  const [pool, setPool] = useState<Pool | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [questions, setQuestions] = useState<PlayerEntry[]>([]);
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [error, setError] = useState<string | null>(null);

  const startGame = (selectedPool: Pool) => {
    setPool(selectedPool);
    setError(null);

    // Combine every year in the pool, stamping each player with the year it came from.
    const data = selectedPool.years.flatMap((y) =>
      (DATA_BY_YEAR[y] ?? []).map((p) => ({ ...p, year: y }))
    );

    if (data.length === 0) {
      setError(`No players found for ${selectedPool.label}.`);
      setPhase("select");
      return;
    }

    const level = LEVELS.find((l) => l.id === difficulty)!;
    setQuestions(pickQuestions(data, level, Math.min(QUESTION_COUNT, data.length)));
    setIndex(0);
    setPicked(null);
    setAnswers([]);
    setPhase("playing");
  };

  const choose = (manager: string) => {
    if (picked !== null) return;
    setPicked(manager);
    setAnswers((prev) => [...prev, { player: questions[index], picked: manager }]);
  };

  const next = () => {
    if (index + 1 >= questions.length) {
      setPhase("done");
    } else {
      setIndex(index + 1);
      setPicked(null);
    }
  };

  const reset = () => {
    setPhase("select");
    setPool(null);
  };

  const score = answers.filter((a) => a.picked === a.player.manager).length;

  /* ---------- Screens ---------- */
  if (phase === "select") {
    return (
      <main className="mg">
        <section className="mg-card mg-intro">
          <h1 className="mg-title">Guess The Manager</h1>
          <p className="mg-lede">
            Pick a difficulty and a game mode. We'll show you {QUESTION_COUNT} players, and you name the manager who
            had them.
          </p>

          {error && (
            <p className="mg-error" role="alert">
              {error}
            </p>
          )}

          <h2 className="mg-label">Difficulty</h2>
          <div className="mg-levels" role="group" aria-label="Choose a difficulty">
            {LEVELS.map((l) => (
              <button
                key={l.id}
                className={`mg-btn mg-level ${difficulty === l.id ? "is-selected" : ""}`}
                aria-pressed={difficulty === l.id}
                onClick={() => setDifficulty(l.id)}
              >
                <span className="mg-level-name">{l.label}</span>
                <span className="mg-level-blurb">{l.blurb}</span>
              </button>
            ))}
          </div>

          <h2 className="mg-label">Single season (tap to start)</h2>
          <div className="mg-years" role="group" aria-label="Choose a season">
            {SINGLE_POOLS.map((p) => (
              <button key={p.id} className="mg-btn mg-btn-year" onClick={() => startGame(p)}>
                {p.label}
              </button>
            ))}
          </div>

          <h2 className="mg-label">Multiple seasons</h2>
          <div className="mg-modes" role="group" aria-label="Choose a multi-season mode">
            {MULTI_POOLS.map((p) => (
              <button key={p.id} className="mg-btn mg-mode" onClick={() => startGame(p)}>
                <span className="mg-level-name">{p.label}</span>
                <span className="mg-level-blurb">{p.blurb}</span>
              </button>
            ))}
          </div>
        </section>
      </main>
    );
  }

  if (phase === "done") {
    const misses = answers.filter((a) => a.picked !== a.player.manager);
    return (
      <main className="mg">
        <section className="mg-card mg-results">
          <p className="mg-meta">
            {pool?.label}, {LEVELS.find((l) => l.id === difficulty)?.label}
          </p>
          <h1 className="mg-score">
            {score}
            <span className="mg-score-total">/{answers.length}</span>
          </h1>
          <p className="mg-lede">{verdict(score, answers.length)}</p>

          {misses.length > 0 && (
            <div className="mg-misses">
              <h2 className="mg-subhead">Ones you missed</h2>
              <ul>
                {misses.map((m) => (
                  <li key={`${m.player.player_id}-${m.player.year}`}>
                    <span className="mg-miss-player">
                      {m.player.player_name}
                      {pool && pool.years.length > 1 && (
                        <span className="mg-miss-year"> ({m.player.year})</span>
                      )}
                    </span>
                    <span className="mg-miss-detail">
                      <s>{m.picked}</s> → <strong>{m.player.manager}</strong>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mg-actions">
            <button className="mg-btn mg-btn-primary" onClick={() => pool && startGame(pool)}>
              Play again
            </button>
            <button className="mg-btn mg-btn-ghost" onClick={reset}>
              Change mode
            </button>
          </div>
        </section>
      </main>
    );
  }

  const current = questions[index];
  const isLast = index + 1 >= questions.length;
  const wasCorrect = picked === current.manager;

  return (
    <main className="mg">
      <section className="mg-card">
        <header className="mg-header">
          <button className="mg-quit" onClick={reset} aria-label="Quit game">
            ✕
          </button>
          <div className="mg-progress" aria-hidden="true">
            <div
              className="mg-progress-bar"
              style={{ width: `${((index + (picked ? 1 : 0)) / questions.length) * 100}%` }}
            />
          </div>
          <span className="mg-counter">
            {index + 1}/{questions.length}
          </span>
        </header>

        <div className="mg-player">
          {pool && pool.years.length > 1 && <span className="mg-year-chip">{current.year}</span>}
          <p className="mg-meta">
            {pool && pool.years.length > 1
              ? "Who had this player that season?"
              : `Who had this player in ${current.year}?`}
          </p>
          <h1 className="mg-player-name">{current.player_name}</h1>
        </div>

        <div className="mg-options" role="group" aria-label="Managers">
          {(MANAGERS_BY_YEAR[current.year] ?? []).map((m) => {
            let state = "";
            if (picked !== null) {
              if (m === current.manager) state = "is-correct";
              else if (m === picked) state = "is-wrong";
              else state = "is-dim";
            }
            return (
              <button
                key={m}
                className={`mg-btn mg-option ${state}`}
                onClick={() => choose(m)}
                disabled={picked !== null}
              >
                <span>{m}</span>
                {state === "is-correct" && <span aria-label="correct">✓</span>}
                {state === "is-wrong" && <span aria-label="incorrect">✗</span>}
              </button>
            );
          })}
        </div>

        <footer className="mg-footer" aria-live="polite">
          {picked !== null && (
            <>
              <p className={`mg-feedback ${wasCorrect ? "good" : "bad"}`}>
                {wasCorrect ? "Correct." : `Nope. That was ${current.manager}.`}
              </p>
              <button className="mg-btn mg-btn-primary" onClick={next} autoFocus>
                {isLast ? "See results" : "Next player"}
              </button>
            </>
          )}
        </footer>
      </section>
    </main>
  );
}
