import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./HallOfFame.css";

interface Award {
  type: "champion" | "lastPlace" | "regularSeason" | "bestManager" | "luckiest" | "unluckiest" | "highScore" | "lowScore";
  title: string;
  name: string;
  username: string;
  detail: string;
  linkable?: boolean;
}

interface YearRecord {
  year: string;
  awards: Award[];
}

const AWARD_META: Record<Award["type"], { icon: string; label: string; variant: "gold" | "coal" | "neutral" }> = {
  champion: { icon: "🏆", label: "Champion", variant: "gold" },
  lastPlace: { icon: "🐢", label: "Last Place", variant: "coal" },
  regularSeason: { icon: "📅", label: "Regular Season Winner", variant: "neutral" },
  bestManager: { icon: "🧠", label: "Best Fantasy Manager", variant: "neutral" },
  luckiest: { icon: "🍀", label: "Luckiest", variant: "neutral" },
  unluckiest: { icon: "💀", label: "Unluckiest", variant: "neutral" },
  highScore: { icon: "🔥", label: "Highest Scoring Week", variant: "neutral" },
  lowScore: { icon: "🥶", label: "Lowest Scoring Week", variant: "neutral" },
};

const seasons: YearRecord[] = [
  {
    year: "2023",
    awards: [
      { type: "champion", title: "Champion", name: "Flow", username: "For Pitts and Giggles", detail: "", linkable: true },
      { type: "lastPlace", title: "Last Place", name: "Revy", username: "Revy's Konstruction", detail: "", linkable: true },
      { type: "regularSeason", title: "Regular Season Winner", name: "Flow", username: "For Pitts and Giggles", detail: "" },
      { type: "highScore", title: "Highest Scoring Week", name: "Tsuga", username: "Tsuga's Tuck Shop", detail: "206.88" },
      { type: "lowScore", title: "Lowest Scoring Week", name: "The Sage", username: "The Sage's Playmakers", detail: "53.96" },
    ],
  },
  {
    year: "2024",
    awards: [
      { type: "champion", title: "Champion", name: "Revy", username: "Revy's Konstruction", detail: "", linkable: true },
      { type: "lastPlace", title: "Last Place", name: "Spartan", username: "Sparty's Sigmas", detail: "", linkable: true },
      { type: "regularSeason", title: "Regular Season Winner", name: "Oscrop", username: "Ozzy Stick", detail: "" },
      { type: "highScore", title: "Highest Scoring Week", name: "Spartan", username: "Sparty's Sigmas", detail: "181.2" },
      { type: "lowScore", title: "Lowest Scoring Week", name: "Revy", username: "Revy's Konstruction", detail: "61.72" },
    ],
  },
  {
    year: "2025",
    awards: [
      { type: "champion", title: "Champion", name: "Flow", username: "Go With The Flow", detail: "", linkable: true },
      { type: "lastPlace", title: "Last Place", name: "Revy", username: "Revy's Konstruction", detail: "", linkable: true },
      { type: "regularSeason", title: "Regular Season Winner", name: "Rubik", username: "No Punts Intended", detail: "" },
      { type: "highScore", title: "Highest Scoring Week", name: "Tsuga", username: "Tsuga's Tuck Shop", detail: "168.4" },
      { type: "lowScore", title: "Lowest Scoring Week", name: "Maître 'D", username: "Maître Magic", detail: "62.82" },
    ],
  },
];

const HallOfFame: React.FC = () => {
  const navigate = useNavigate();
  const [openYear, setOpenYear] = useState<string>("");

  const goToProfile = (username: string, year: string) => {
    // Hook this up to your own route/page, e.g. /players/:slug
    navigate(`/hall-of-fame/${username}/${year}`);
  };

  const toggleYear = (year: string) => {
    setOpenYear((prev) => (prev === year ? "" : year));
  };

  return (
    <div className="hof-page">
      <div className="hof-header">
        <h1 className="hof-title">🏈 League Hall of Fame</h1>
        <p className="hof-subtitle">Every champion, every disaster, every season on record</p>
      </div>

      <div className="hof-trophy-wrap">
        <img src="FantasyTrophy.jpg" alt="Trophy" className="hof-trophy-img" />
      </div>

      <div className="hof-seasons">
        {seasons.map((season) => {
          const isOpen = openYear === season.year;
          const champion = season.awards.find((a) => a.type === "champion");

          return (
            <section key={season.year} className={`hof-season-card ${isOpen ? "hof-season-card--open" : ""}`}>
              <button
                className="hof-season-header"
                onClick={() => toggleYear(season.year)}
                aria-expanded={isOpen}
              >
                <div className="hof-season-header-left">
                  <span className="hof-season-year">{season.year}</span>
                  {champion && (
                    <span className="hof-season-champion">
                      🏆 {champion.name} — {champion.username}
                    </span>
                  )}
                </div>
                <span className={`hof-chevron ${isOpen ? "hof-chevron--open" : ""}`}>▾</span>
              </button>

              {isOpen && (
                <div className="hof-award-grid">
                  {season.awards.map((award) => {
                    const meta = AWARD_META[award.type];
                    const isLinkable = !!award.linkable;
                    const Tag = isLinkable ? "button" : "div";

                    return (
                      <Tag
                        key={award.type}
                        className={`hof-award-card hof-award-card--${meta.variant} ${isLinkable ? "hof-award-card--linkable" : ""}`}
                        onClick={isLinkable ? () => goToProfile(award.username, season.year) : undefined}
                      >
                        <div className="hof-award-icon">{meta.icon}</div>
                        <div className="hof-award-body">
                          <span className="hof-award-label">{meta.label}</span>
                          <span className="hof-award-name">
                             {award.username}({award.name})
                          </span>
                          {award.detail && <span className="hof-award-detail">{award.detail}</span>}
                          {isLinkable && <span className="hof-award-see-more">See more →</span>}
                        </div>
                      </Tag>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
};

export default HallOfFame;