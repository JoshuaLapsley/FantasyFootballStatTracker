import React from "react";
import RosterTable from "../../../Components/RosterTable";
import "./Connor2023.css";
import HallOfFameBackButton from "../../Components/HallOfFameBackButton";

const Connor2023: React.FC = () => {
  return (
    <div className="player-page">
      <HallOfFameBackButton />
      <header className="punishment-header">
        <h1 className="punishment-title">The Fruit Check</h1>
        <p className="punishment-subtitle">Connor's Punishment · 2023</p>
      </header>

      <section className="punishment-story">
        <p>
          The original punishment involved having to sleep naked overnight in the treehouse,
          while everyone spent the night below making sure you couldn't leave. However the
          punishment was changed due to people having responsibilities.
        </p>
        <p>
          The changed punishment was a bit complicated but it went like this: every week for
          all 7 weeks at camp, Revy had a specific fruit, which would grow in size every week.
          He had to carry this fruit with him at all times, and people from the league at any
          time (once per day) hit Revy with a fruit check. If he did not have his fruit on him,
          he had to double the amount of fruit he had. The fruit ranged in sizes from grapes to
          watermelon. At one point he had to keep 4 watermelons on him at all times.
        </p>
      </section>

      <section className="punishment-media">
        <img src="/ConnorPunishment2023/BrokenGrape.jpeg" alt="Broken Grape" className="punishment-image" />
        <img src="/ConnorPunishment2023/Fruit.jpeg" alt="Fruit" className="punishment-image" />
        <video controls width="400" className="punishment-video">
          <source src="/ConnorPunishment2023/test.MOV" />
          Your browser doesn't support this video.
        </video>
      </section>

      <section>
        <RosterTable team={"Revy’s Konstruction"} year={"2023"} week={"last"} />
      </section>
    </div>
  );
};

export default Connor2023;