import React from "react";
import { useNavigate } from "react-router-dom";
import "./HallOfFame.css";

interface Member {
  name: string;
  username: string;
  year: string;
  detail: string;
}

const winners: Member[] = [
  { name: "Zach", username: "For Pitts and Giggles", year: "2023", detail: "Credits Josh Allen" },
  { name: "Connor", username: "Revy’s Konstruction", year: "2024", detail: "Bounce Back Year" },
  { name: "Zach", username: "Go With The Flow", year: "2025", detail: "Lost 1st Round Pick Early in Season, and Still Won" },
];

const losers: Member[] = [
  { name: "Connor", username: "Revy’s Konstruction", year: "2023", detail: "Fruit Punishment" },
  { name: "Jackson", username: "Sparty's Sigmas", year: "2024", detail: "Had to go Vegetarian for a Month" },
  { name: "Connor", username: "Revy’s Konstruction", year: "2025", detail: "6-12-18-24" },
];

const HallOfFame: React.FC = () => {
  const navigate = useNavigate();

  const goToProfile = (username: string, year: string ) => {
    // Hook this up to your own route/page, e.g. /players/:slug
    navigate(`/hall-of-fame/${username}/${year}`);
  };

  const renderList = (members: Member[], variant: "gold" | "coal") => (
    <ul className="hof-list">
      {members.map((m) => (
        <li key={m.username}>
          <button
            onClick={() => goToProfile(m.username, m.year)}
            className={`hof-row ${variant === "gold" ? "hof-row--gold" : "hof-row--coal"}`}
          >
            <span className="hof-row-name">{`${m.name} - ${m.username}`}</span>
            <span className="hof-row-meta">
              {m.year} · {m.detail}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="hof-page">
      <div className="hof-header">
        <h1 className="hof-title">Hall of Fame</h1>
      </div>

      <div className="hof-columns">
        <section className="hof-column">
          <h2 className="hof-column-title hof-column-title--gold">🏆 Champions</h2>
          {renderList(winners, "gold")}
        </section>

        <section className="hof-column">
          <h2 className="hof-column-title hof-column-title--coal">🐢Last Place</h2>
          {renderList(losers, "coal")}
        </section>
      </div>
      < br />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
        <img
          src="FantasyTrophy.jpg"
          alt="Trophy"
          style={{
            width: "40%",
            maxWidth: "220px",
            minWidth: "120px",
            height: "auto",
            objectFit: "cover",
            borderRadius: "8px",
          }}
        />
      </div>
    </div>
  );
};

export default HallOfFame;
