import React from "react";
import RosterTable from "../../../Components/RosterTable";
import "./Zach2025.css";
import HallOfFameBackButton from "../../Components/HallOfFameBackButton";

const Connor2024: React.FC = () => {

  return (
    <div className="player-page">
      <HallOfFameBackButton />

      <div> Winning Team </div>
      <RosterTable team={"Go With The Flow"} year={"2025"} week={"last"} />
      <div> TO ADD: blurb about winning team </div>
    </div>
  );
};

export default Connor2024;
