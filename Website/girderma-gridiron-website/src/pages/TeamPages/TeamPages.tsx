import React, { useState, useEffect } from "react";
import "./TeamPages.css";

/* =====================================================================
   1) PASTE YOUR GOOGLE SHEETS API URL HERE
   ===================================================================== */
const API_URL = "https://script.googleusercontent.com/macros/echo?user_content_key=AUkAhnR-amOxH-jQhhbt2rdKu0tPqnPoD_8p-NbIbkeRCmy8L_H8Im7CllwpxGXFWrVdMQa2JT6sZnAjzpx_X1PKgugWsXFajsRfAgnNs9eIDR6D36rt7BqISWA0nL_KJQPn47phTz0Aryd5tGDVYqKXLLDpQnhd7OaJdEmTvXt47rveq-KGXnCcqcvunnr-PG-yBmkkme191Hw7QLlVV52FDLx3u2EiCmCkYS2iwuaWMO8AyQX2m9xiCpWvtwZdMYCqc3PtboeOIYWVrOKnBZ5mE1zHYlsVbQ&lib=MiDEjg6dJUQ5OnGJDPzG6dkrwxZh9YfNT";

/* ---------------------------------------------------------------------
   TYPES
------------------------------------------------------------------- */
export interface CampConfig {
  leagueRole?: string;
  yearsWon?: number[];
}

export interface Team {
  campName: string;
  teamName: string;
  leagueRole?: string;
  yearsWon?: number[];
  favouriteFootballTeam?: string;
  favouriteFantasyPlayer?: string;
  bestFantasyMemory?: string;
  worstFantasyMemory?: string;
  thisYearsThoughts?: string;
  lastUpdated?: string;
}

interface ApiRow {
  "Camp Name"?: string;
  "Fantasy Team Name"?: string;
  "Favourite Football Team"?: string | number;
  "Favourite Fantasy Player"?: string | number;
  "Best Fantasy Memory"?: string | number;
  "Worst Fantasy Memory"?: string | number;
  "Thoughts on this year's season"?: string | number;
  "Last Updated"?: string;
}

type FieldType = "text" | "longtext";
type FieldTone = "default" | "good" | "bad";

interface FieldDef {
  key: keyof Team;
  label: string;
  type: FieldType;
  tone?: FieldTone;
}

type Status = "loading" | "ready" | "error";

/* =====================================================================
   2) PREDEFINED CAMP CONFIG
   Key = the exact "Camp Name" string that comes back from the sheet.
   Fill in / correct these to match your real camp names.
   leagueRole and yearsWon are NOT in the sheet, so they live here and
   get merged onto whatever the API returns for that camp.
   ===================================================================== */
const CAMP_CONFIG: Record<string, CampConfig> = {
  "The Sage": { leagueRole: "Developer of the League" },
  "Flow": { leagueRole: "Commissioner", yearsWon: [2023, 2025] },
  "Oscorp": { leagueRole: "Treasurer" },
  "Revy": { yearsWon: [2024] },
  "Girder": {},
  "Tsuga": {},
  "Old Man Argo": {},
  "Maître D'": { leagueRole: "League Statistician" },
  "Falcon": {},
  "Hokkaido": {},
  "Rubik": {},
  "Omaha": {},
  "Paddy": {},
  "Supernova": {},
};

/* ---------------------------------------------------------------------
   FIELD SCHEMA
   To add a new property in the future:
     1. Add the key to the Team interface above.
     2. Add it to rowToTeam() below so it gets pulled off the row.
     3. Add a field definition below (key must match what rowToTeam sets).
   That's it — the detail card reads from this array automatically.
------------------------------------------------------------------- */
const FIELD_DEFS: FieldDef[] = [
  { key: "favouriteFootballTeam", label: "Favourite Football Team", type: "text" },
  { key: "favouriteFantasyPlayer", label: "Favourite Fantasy Player", type: "text" },
  { key: "bestFantasyMemory", label: "Best Fantasy Memory", type: "longtext", tone: "good" },
  { key: "worstFantasyMemory", label: "Worst Fantasy Memory", type: "longtext", tone: "bad" },
  { key: "thisYearsThoughts", label: "This Year's Thoughts", type: "longtext" },
];

/* --------------------------- helpers --------------------------- */
const initials = (name = ""): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

const CREST_COLORS = ["#D9A62E", "#5B8C7B", "#B23A2E", "#3E6E8E", "#8C6B4F", "#6E5B8C"];
const hashString = (str = ""): number => {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
};
const crestColor = (key: string): string => CREST_COLORS[hashString(key) % CREST_COLORS.length];

const clean = (val: unknown): string | undefined => {
  if (val === undefined || val === null) return undefined;
  const str = String(val).trim();
  return str.length > 0 ? str : undefined;
};

/* ---------------------------------------------------------------------
   Turn one row from the Google Sheet into a Team object, merging in
   the predefined config for that camp.
------------------------------------------------------------------- */
function rowToTeam(row: ApiRow): Team {
  const campName = clean(row["Camp Name"]) || "Unknown Camp";
  const config = CAMP_CONFIG[campName] || {};

  return {
    campName,
    teamName: clean(row["Fantasy Team Name"]) || campName,
    leagueRole: config.leagueRole,
    yearsWon: config.yearsWon,
    favouriteFootballTeam: clean(row["Favourite Football Team"]),
    favouriteFantasyPlayer: clean(row["Favourite Fantasy Player"]),
    bestFantasyMemory: clean(row["Best Fantasy Memory"]),
    worstFantasyMemory: clean(row["Worst Fantasy Memory"]),
    thisYearsThoughts: clean(row["Thoughts on this year's season"]),
    lastUpdated: clean(row["Last Updated"]),
  };
}

/* --------------------------- component --------------------------- */
export default function TeamPages() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [status, setStatus] = useState<Status>("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [selectedCamp, setSelectedCamp] = useState<string | null>(null);

  useEffect(() => {
    const link = document.createElement("link");
    link.href =
      "https://fonts.googleapis.com/css2?family=Anton&family=Work+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap";
    link.rel = "stylesheet";
    document.head.appendChild(link);
    return () => {
      document.head.removeChild(link);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadTeams() {
      setStatus("loading");
      try {
        const res = await fetch(API_URL);
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data: ApiRow[] = await res.json();
        if (cancelled) return;

        const mapped = (Array.isArray(data) ? data : []).map(rowToTeam);
        setTeams(mapped);
        setSelectedCamp((prev) => prev || mapped[0]?.campName || null);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : "Something went wrong");
        setStatus("error");
      }
    }

    loadTeams();
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = teams.find((t) => t.campName === selectedCamp) || teams[0];

  return (
    <div className="tp-page">
      <header className="tp-header">
        <span className="tp-eyebrow">Team Pages</span>
        <h1 className="tp-title">Girderma Gridiron Team Pages</h1>
        <p className="tp-subtitle">Tap a name to pull their card.</p>
      </header>

      {status === "loading" && (
        <div className="tp-status">
          <span className="tp-spinner" aria-hidden="true" />
          Loading Team Pages…
        </div>
      )}

      {status === "error" && (
        <div className="tp-status tp-status-error">
          Couldn't load the roster: {errorMessage}
        </div>
      )}

      {status === "ready" && (
        <div className="tp-layout">
          <nav className="tp-roster" aria-label="Team roster">
            <ol>
              {teams.map((team) => (
                <li key={team.campName}>
                  <button
                    className={`tp-roster-item ${team.campName === selectedCamp ? "is-active" : ""}`}
                    onClick={() => setSelectedCamp(team.campName)}
                  >
                    <span className="tp-roster-name">{team.campName}</span>
                    <span className="tp-roster-arrow">→</span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>

          <section className="tp-card-wrap" aria-live="polite">
            {selected && <TeamCard team={selected} />}
          </section>
        </div>
      )}
    </div>
  );
}

function TeamCard({ team }: { team: Team }) {
  return (
    <article className="tp-card">
      <div className="tp-card-top">
        <div className="tp-crest" style={{ background: crestColor(team.campName) }}>
          <span>{initials(team.campName)}</span>
        </div>
        <div className="tp-card-heading">
          <span className="tp-camp-name">{team.campName}</span>
          <h2>{team.teamName}</h2>
          {team.leagueRole && <span className="tp-role-tag">{team.leagueRole}</span>}
        </div>
      </div>

      {team.yearsWon && team.yearsWon.length > 0 && (
        <div className="tp-years">
          {team.yearsWon
            .slice()
            .sort((a, b) => b - a)
            .map((year) => (
              <span className="tp-year-badge" key={year}>
                🏆 {year}
              </span>
            ))}
        </div>
      )}

      <dl className="tp-fields">
        {FIELD_DEFS.map((field) => {
          const value = team[field.key] as string | undefined;
          if (!value) return null;
          return (
            <div className={`tp-field tp-field-${field.tone || "default"}`} key={String(field.key)}>
              <dt>{field.label}</dt>
              <dd>{value}</dd>
            </div>
          );
        })}
      </dl>
    </article>
  );
}
