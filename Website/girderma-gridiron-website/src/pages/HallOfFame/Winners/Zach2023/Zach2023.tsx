import React from "react";
import RosterTable from "../../../Components/RosterTable";
import "./Zach2023.css";
import HallOfFameBackButton from "../../Components/HallOfFameBackButton";

const Zach2023: React.FC = () => {

  return (
    <div className="player-page">
     <HallOfFameBackButton />

      <div> Winning Team </div>
      <RosterTable team={"For Pitts and Giggles"} year={"2023"} week={"last"} />
      <div> TO ADD: blurb about winning team </div>
    </div>
  );
};

export default Zach2023;
