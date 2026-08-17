import React, { useState, useEffect } from "react";
import "./TeamPages.css";

/* ---------------------------------------------------------------------
   TYPES
------------------------------------------------------------------- */
export interface Team {
  id: number;
  image?: string;
  teamName: string;
  leagueRole?: string;
  favouriteFootballTeam?: string;
  favouriteFantasyPlayer?: string;
  bestFantasyMemory?: string;
  worstFantasyMemory?: string;
  additionalNotes?: string;
  yearsWon?: number[]; // <-- add this
  ReactComponent?: React.ComponentType;
  [key: string]: unknown;
}

type FieldType = "text" | "longtext" | "tag";
type FieldTone = "default" | "good" | "bad";

interface FieldDef {
  key: keyof Team;
  label: string;
  type: FieldType;
  tone?: FieldTone;
}

/* ---------------------------------------------------------------------
   FIELD SCHEMA
   To add a new property in the future:
     1. Add its key to the Team interface above.
     2. Add a field definition below (key must match the property name
        on each team object).
     3. Add that same key to each team object in DUMMY_TEAMS (or leave
        it out / empty — blank values are simply not rendered).
   That's it — the roster list and the detail card both read from this
   array, so nothing else needs to change.
------------------------------------------------------------------- */
const FIELD_DEFS: FieldDef[] = [
  { key: "leagueRole", label: "League Role", type: "tag" },
  { key: "favouriteFootballTeam", label: "Favourite Football Team", type: "text" },
  { key: "favouriteFantasyPlayer", label: "Favourite Fantasy Player", type: "text" },
  { key: "bestFantasyMemory", label: "Best Fantasy Memory", type: "longtext", tone: "good" },
  { key: "worstFantasyMemory", label: "Worst Fantasy Memory", type: "longtext", tone: "bad" },
  { key: "additionalNotes", label: "Additional Notes", type: "longtext" },
];



const PotTracker: React.FC = () => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "8px",
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: "12px",
      fontWeight: 500,
      letterSpacing: "0.03em",
      color: "rgba(27,27,27,0.55)",
      background: "rgba(27,27,27,0.04)",
      border: "1.5px dashed rgba(27,27,27,0.2)",
      padding: "8px 14px",
      borderRadius: "8px",
    }}
  >
    <span style={{ fontSize: "14px" }}>🚧</span>
    <span>Pot Tracker — Coming Soon</span>
  </div>
);

const DUMMY_TEAMS: Team[] = [
  {
    id: 1,
    image: "",
    teamName: "The Sage's PlayMakers",
    leagueRole: "Developer of the League",
    favouriteFootballTeam: "Carolina Panthers",
    favouriteFantasyPlayer: "De'Von Achane",
    bestFantasyMemory:
      "Tuning into the most random games, to watch my kicker hopefuly get me 10 points.",
    worstFantasyMemory:
      "Isaiah Likely dropping a snowman in the playoffs, when I just needed him to get 1 reception to win the week.",
    additionalNotes: "Luther Burden is the worst Fantasy Player this year."
  },
  {
    id: 2,
    image: "",
    teamName: "Flow Brrr",
    leagueRole: "Comissioner",
    yearsWon: [2024, 2026],
        
  },
  {
    id: 3,
    image: "",
    teamName: "Ozzy Stick",
    leagueRole: "Treasurer",
    ReactComponent: () => <PotTracker />,
  },
  {
    id: 4,
    image: "",
    teamName: "Revy's Konstruction",
    yearsWon: [2025],
        
  },
  {
    id: 5,
    image: "",
    teamName: "You Gotta Be Falcon Kiddin Me",   
  },
  {
    id: 6,
    image: "",
    teamName: "Girder's 6 Cookies",   
  },
  {
    id: 7,
    image: "",
    teamName: "Big Bad Hokkkk",   
  },
  {
    id: 8,
    image: "",
    teamName: "Hunter's Hunters",   
  },
  {
    id: 9,
    image: "",
    leagueRole: "League Statistician",
    teamName: "Maitre Stick",   
  },
  {
    id: 10,
    image: "",
    teamName: "No Punts Intented",   
  },
  {
    id: 11,
    image: "",
    teamName: "Omaha Beach Real Estate",   
  },
  {
    id: 12,
    image: "",
    teamName: "Pad D's",   
  },
  {
    id: 13,
    image: "",
    teamName: "Supernova's Studs",   
  },
  {
    id: 14,
    image: "",
    teamName: "Tsuga's Tuck Shop",   
  },
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
const crestColor = (id: number): string => CREST_COLORS[id % CREST_COLORS.length];

/* --------------------------- component --------------------------- */
export default function TeamPages() {
  const [selectedId, setSelectedId] = useState<number>(DUMMY_TEAMS[0].id);
  const selected = DUMMY_TEAMS.find((t) => t.id === selectedId) || DUMMY_TEAMS[0];

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

  return (
    <div className="tp-page">
      <header className="tp-header">
        <span className="tp-eyebrow">Team Pages</span>
        <h1 className="tp-title">League Roster</h1>
        <p className="tp-subtitle">Tap a team name to pull their card.</p>
      </header>

      <div className="tp-layout">
        {/* Roster list */}
        <nav className="tp-roster" aria-label="Team roster">
          <ol>
            {DUMMY_TEAMS.map((team, i) => (
              <li key={team.id}>
                <button
                  className={`tp-roster-item ${team.id === selectedId ? "is-active" : ""}`}
                  onClick={() => setSelectedId(team.id)}
                >
                  <span className="tp-roster-num">{String(i + 1).padStart(2, "0")}</span>
                  <span className="tp-roster-name">{team.teamName}</span>
                  <span className="tp-roster-arrow">→</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        {/* Detail card */}
        <section className="tp-card-wrap" aria-live="polite">
          <TeamCard team={selected} />
        </section>
      </div>
    </div>
  );
}

function TeamCard({ team }: { team: Team }) {
  const CustomComponent = team.ReactComponent;

  return (
    <article className="tp-card">
      <div className="tp-card-top">
        <div className="tp-crest" style={{ background: crestColor(team.id) }}>
          {team.image ? (
            <img src={team.image} alt={team.teamName} />
          ) : (
            <span>{initials(team.teamName)}</span>
          )}
        </div>
        <div className="tp-card-heading">
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
      {CustomComponent && (
        <div className="tp-custom-slot">
          <CustomComponent />
        </div>
      )}

      <dl className="tp-fields">
        {FIELD_DEFS.filter((f) => f.type !== "tag").map((field) => {
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
