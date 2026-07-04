import React from "react";
import RosterTable from "../../../Components/RosterTable";
import "./Jackson2024.css";
import HallOfFameBackButton from "../../Components/HallOfFameBackButton";

const Jackson2024: React.FC = () => {
  return (
    <div className="player-page">
      <HallOfFameBackButton />
      <header className="punishment-header">
        <h1 className="punishment-title">Vegetarian For a Month</h1>
        <p className="punishment-subtitle">Jackson's Punishment · 2024</p>
      </header>

      <section className="punishment-story">
        <p>
          Jackson had a tough year, that mostly just invovled most of his players getting injured. Including the first overall pick of the draft
          Christian McCaffrey.
        </p>
        <p>
          Picking a punishment this year was challenging. Everyone had a ton of ideas but it took a while for the league to decide on the punishent.
          Eventually it was put to a vote, and the punishment was selected was going Vegetarian for a month.
        </p>
        <p>
          The loser could choose which month they wanted to do the punishment, and Jackson selected January as his month of choice.
        </p>
        <p>
          There was a funny story, where Jackson was over at SupernovaMaAndPa's House for dinner, and they were having Pizza. And he had to instead
          choose the Vegetarian option that night. He didn't tell anyone about it, but SupernovaMa sent Supernova a text saying that he did in fact not eat meat.
        </p>
      </section>

      <section className="punishment-media">
        <img src="/JacksonPunishment2024/Proof.jpg" alt="Proof" className="punishment-image" />
        
      </section>

      <section>
        <RosterTable team={"Sparty's Sigmas"} year={"2024"} week={"last"} />
      </section>
    </div>
  );
};

export default Jackson2024;